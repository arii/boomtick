import { z } from "zod";
import { AttemptRecord, ProviderChainExhaustedError, WorkflowValidationError } from "./errors.js";
import { invokeWorkflow, formatZodIssues, validateWorkflowInput, WorkflowRegistry } from "./registry.js";

// Mirrors RunWorkflowInput in the generated MCP contract (mcp/src/tools/contract.ts).
// The gateway re-validates so it stays usable standalone and so malformed
// requests are rejected even if a caller skips the MCP schema parse.
const gatewayInputSchema = z.object({
  workflow: z.string().min(1, "workflow id is required"),
  input: z.record(z.string(), z.any()).optional(),
});

export interface RunWorkflowReceipt {
  status: "success" | "error";
  workflow?: string;
  result?: Record<string, unknown> | null;
  steps: AttemptRecord[];
  tier?: string;
  model?: string;
  error?: string;
}

export interface GatewayDeps {
  registry: WorkflowRegistry;
}

/**
 * The run_workflow gateway: validate → look up → invoke → receipt.
 * Strict and deterministic: unknown ids and malformed inputs never reach a
 * graph, and every failure mode maps to a distinct error message.
 */
export async function runWorkflowGateway(rawInput: unknown, deps: GatewayDeps): Promise<RunWorkflowReceipt> {
  const parsed = gatewayInputSchema.safeParse(rawInput);
  if (!parsed.success) {
    throw new WorkflowValidationError(`Malformed run_workflow request — ${formatZodIssues(parsed.error)}`);
  }

  const definition = deps.registry.require(parsed.data.workflow);
  const validatedInput = validateWorkflowInput<Record<string, unknown>>(definition, parsed.data.input);

  try {
    const finalState = await invokeWorkflow(definition, validatedInput);
    if (finalState.error) {
      return {
        status: "error",
        workflow: definition.id,
        result: null,
        steps: finalState.steps,
        tier: finalState.tier,
        model: finalState.model,
        error: finalState.error,
      };
    }
    return {
      status: "success",
      workflow: definition.id,
      result: finalState.result ?? null,
      steps: finalState.steps,
      tier: finalState.tier,
      model: finalState.model,
    };
  } catch (error) {
    if (error instanceof ProviderChainExhaustedError) {
      return {
        status: "error",
        workflow: definition.id,
        result: null,
        steps: error.attempts as AttemptRecord[],
        error: error.message,
      };
    }
    throw error;
  }
}
