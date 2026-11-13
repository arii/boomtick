import { z } from "zod";
import { ChatOllama } from "@langchain/ollama";
import { ChatOpenAI } from "@langchain/openai";
import { StructuredCandidate } from "./chain.js";
import { ProviderEnvConfig, LOCAL_NUM_CTX, OPENROUTER_BASE_URL, NEBIUS_BASE_URL, WORKFLOW_TEMPERATURE } from "./config.js";
import { SchemaRejectionError } from "../errors.js";

// Each factory returns an ALREADY-WRAPPED candidate: withStructuredOutput is
// applied per provider BEFORE the chain composes fallbacks, so every tier
// returns the same typed output (research art_7FsLzVOd §3).

/** Local Ollama candidate — native json_schema structured outputs. */
function localCandidate<T>(schema: z.ZodType<T>, config: ProviderEnvConfig, model?: string): StructuredCandidate<T> {
  const chat = new ChatOllama({
    model: model ?? config.localStructuredModel,
    baseUrl: config.ollamaBaseUrl,
    temperature: WORKFLOW_TEMPERATURE,
    numCtx: LOCAL_NUM_CTX,
  });
  return {
    tier: "local",
    model: model ?? config.localStructuredModel,
    invoke: async (input: string) => {
      const structured = chat.withStructuredOutput(schema);
      try {
        return (await structured.invoke(input)) as T;
      } catch (error) {
        // Ollama structured-output failures surface as generic invoke errors;
        // re-wrap so the chain sees the schema contract, not transport noise.
        if (error instanceof Error && /json|schema|parse/i.test(error.message)) {
          throw new SchemaRejectionError(`local tier returned schema-invalid output: ${error.message}`);
        }
        throw error;
      }
    },
  };
}

/**
 * OpenRouter candidate over the OpenAI-compatible endpoint. Uses the
 * function_calling method (json_schema support varies by pinned model) and
 * counts on the pinned model; 429s classify as transient and burn the
 * 50/day free budget, so the receipt records quota exhaustion explicitly.
 */
function openRouterCandidate<T>(schema: z.ZodType<T>, config: ProviderEnvConfig): StructuredCandidate<T> {
  if (!config.openRouterApiKey || !config.openRouterModel) {
    throw new Error("OpenRouter candidate requested but OPENROUTER_API_KEY/OPENROUTER_MODEL are not configured.");
  }
  const chat = new ChatOpenAI({
    model: config.openRouterModel,
    apiKey: config.openRouterApiKey,
    temperature: WORKFLOW_TEMPERATURE,
    configuration: { baseURL: OPENROUTER_BASE_URL },
  });
  return {
    tier: "openrouter",
    model: config.openRouterModel,
    invoke: async (input: string) => {
      const structured = chat.withStructuredOutput(schema, { method: "functionCalling" });
      return (await structured.invoke(input)) as T;
    },
  };
}

/** Nebius candidate over the OpenAI-compatible Token Factory endpoint. */
function nebiusCandidate<T>(schema: z.ZodType<T>, config: ProviderEnvConfig): StructuredCandidate<T> {
  if (!config.nebiusApiKey || !config.nebiusModel) {
    throw new Error("Nebius candidate requested but NEBIUS_API_KEY/NEBIUS_MODEL are not configured.");
  }
  const chat = new ChatOpenAI({
    model: config.nebiusModel,
    apiKey: config.nebiusApiKey,
    temperature: WORKFLOW_TEMPERATURE,
    configuration: { baseURL: NEBIUS_BASE_URL },
  });
  return {
    tier: "nebius",
    model: config.nebiusModel,
    invoke: async (input: string) => {
      // OpenAI-wire-compatible; function calling is the safest common
      // denominator across Nebius models (capability-dependent per model).
      const structured = chat.withStructuredOutput(schema, { method: "functionCalling" });
      return (await structured.invoke(input)) as T;
    },
  };
}

/**
 * Build the full failover list in order (local → openrouter → nebius),
 * degrading to local-only when cloud keys are absent. The caller surfaces
 * the degradation through the receipt rather than failing silently.
 */
export function buildCandidateList<T>(schema: z.ZodType<T>, config: ProviderEnvConfig): StructuredCandidate<T>[] {
  const candidates: StructuredCandidate<T>[] = [localCandidate(schema, config)];
  if (config.openRouterApiKey && config.openRouterModel) {
    candidates.push(openRouterCandidate(schema, config));
  }
  if (config.nebiusApiKey && config.nebiusModel) {
    candidates.push(nebiusCandidate(schema, config));
  }
  return candidates;
}
