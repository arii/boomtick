import { END, START, StateGraph } from "@langchain/langgraph";
import { z } from "zod";
import { AttemptRecord, ProviderChainExhaustedError, SchemaRejectionError } from "../errors.js";
import { createStructuredChain, StructuredCandidate } from "../providers/chain.js";
import { ProviderEnvConfig } from "../providers/config.js";
import { buildCandidateList } from "../providers/factory.js";
import { WorkflowDefinition } from "../registry.js";
import { WorkflowState } from "../state.js";

const structuredExtractInputSchema = z.object({
  text: z.string().min(1).describe("Text to extract fields from."),
});

type StructuredExtractInput = z.infer<typeof structuredExtractInputSchema>;

const structuredExtractOutputSchema = z.object({
  summary: z.string().describe("One-sentence summary of the text."),
  tags: z.array(z.string()).describe("Zero to five topical tags."),
});

export type StructuredExtractOutput = z.infer<typeof structuredExtractOutputSchema>;

export interface StructuredExtractDeps {
  /** Candidate list override for tests; defaults to the env-driven chain. */
  candidates?: readonly StructuredCandidate<StructuredExtractOutput>[];
  sleep?: (ms: number) => Promise<void>;
}

const MAX_TAGS = 5;

// Constrained extraction: one LLM step, tiny schema, ONE repair attempt that
// feeds the validation error back to the same tier — never a retry loop.
// Open-ended tool choice is deliberately absent; that is cloud-agent territory.
export function createStructuredExtractWorkflow(
  config: ProviderEnvConfig,
  deps: StructuredExtractDeps = {},
): WorkflowDefinition {
  const chain = createStructuredChain<StructuredExtractOutput>({
    candidates: deps.candidates ?? buildCandidateList(structuredExtractOutputSchema, config),
    validate: validateExtraction,
    sleep: deps.sleep,
  });

  const graph = new StateGraph(WorkflowState)
    .addNode("extract", extractNode(chain))
    .addNode("repair", repairNode(chain))
    .addEdge(START, "extract")
    .addConditionalEdges("extract", routeAfterExtract, { repair: "repair", done: END })
    .addEdge("repair", END)
    .compile();

  return {
    id: "structured_extract",
    description:
      "Extract {summary, tags} from free text with the structured-output provider chain (local first). One repair attempt on schema rejection.",
    inputSchema: structuredExtractInputSchema,
    graph,
  };
}

function validateExtraction(value: unknown): StructuredExtractOutput {
  const parsed = structuredExtractOutputSchema.safeParse(value);
  if (!parsed.success) {
    const issues = parsed.error.issues.map((issue) => `${issue.path.join(".")}: ${issue.message}`).join("; ");
    throw new SchemaRejectionError(`extraction output failed schema: ${issues}`);
  }
  // Restraint guard: a 3-4B model asked for "some tags" will happily emit
  // dozens — clamp deterministically instead of trusting the model.
  return { ...parsed.data, tags: parsed.data.tags.slice(0, MAX_TAGS) };
}

type Chain = ReturnType<typeof createStructuredChain<StructuredExtractOutput>>;

function buildExtractPrompt(input: StructuredExtractInput, previousError?: string): string {
  const base = `Extract a summary and topical tags from the following text. Text: ${input.text}`;
  return previousError ? `${base}\n\nYour previous answer was rejected: ${previousError}. Fix it.` : base;
}

/** Pull the per-tier attempts out of a chain failure so receipts keep the trace. */
function attemptsFromChainError(error: unknown): AttemptRecord[] {
  return error instanceof ProviderChainExhaustedError ? ([...error.attempts] as AttemptRecord[]) : [];
}

function extractNode(chain: Chain) {
  return async (state: typeof WorkflowState.State) => {
    const input = state.input as StructuredExtractInput;
    try {
      const call = await chain.run(buildExtractPrompt(input));
      return {
        result: call.value as unknown as Record<string, unknown>,
        tier: call.tier,
        model: call.model,
        steps: call.attempts,
      };
    } catch (error) {
      return { error: describeChainFailure(error), steps: attemptsFromChainError(error) };
    }
  };
}

function repairNode(chain: Chain) {
  return async (state: typeof WorkflowState.State) => {
    const input = state.input as StructuredExtractInput;
    const previousError = state.error ?? "unknown schema rejection";
    try {
      const call = await chain.run(buildExtractPrompt(input, previousError));
      return {
        result: call.value as unknown as Record<string, unknown>,
        tier: call.tier,
        model: call.model,
        error: undefined,
        steps: call.attempts,
      };
    } catch (error) {
      return { error: `repair attempt failed — ${describeChainFailure(error)}`, steps: attemptsFromChainError(error) };
    }
  };
}

function routeAfterExtract(state: typeof WorkflowState.State): "repair" | "done" {
  return state.error ? "repair" : "done";
}

function describeChainFailure(error: unknown): string {
  return error instanceof Error
    ? `structured extraction failed after the provider chain was exhausted: ${error.message}`
    : String(error);
}
