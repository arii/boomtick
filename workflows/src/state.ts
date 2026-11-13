import { Annotation } from "@langchain/langgraph";
import { AttemptRecord, ProviderTier } from "./errors.js";

/**
 * Shared graph state for all workflows. Fixed channels, last-value writes:
 * these are constrained graphs, not free-form agent scratchpads — a node
 * reads what previous nodes wrote and appends its receipt.
 */
export const WorkflowState = Annotation.Root({
  /** Raw, already gateway-validated workflow input. */
  input: Annotation<Record<string, unknown>>({
    reducer: (_prev, next) => next,
    default: () => ({}),
  }),
  /** Per-node receipts, appended in execution order. */
  steps: Annotation<AttemptRecord[]>({
    reducer: (prev, next) => [...prev, ...next],
    default: () => [],
  }),
  /** Final workflow result, written by the terminal node. */
  result: Annotation<Record<string, unknown> | undefined>({
    reducer: (_prev, next) => next,
    default: () => undefined,
  }),
  /** Terminal error message; presence marks a failed run. */
  error: Annotation<string | undefined>({
    reducer: (_prev, next) => next,
    default: () => undefined,
  }),
  /** Provider tier and model that answered LLM steps, for the run receipt. */
  tier: Annotation<ProviderTier | undefined>({
    reducer: (_prev, next) => next,
    default: () => undefined,
  }),
  model: Annotation<string | undefined>({
    reducer: (_prev, next) => next,
    default: () => undefined,
  }),
});

export type WorkflowStateType = typeof WorkflowState.State;
