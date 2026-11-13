// Typed error taxonomy for the workflow runtime. The gateway maps each
// class to a distinct, deterministic error surface — callers must be able
// to tell "you sent a bad request" apart from "the provider chain failed".

export class WorkflowError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "WorkflowError";
  }
}

/** Unknown workflow id, or input that failed the per-workflow schema. */
export class WorkflowValidationError extends WorkflowError {
  constructor(message: string) {
    super(message);
    this.name = "WorkflowValidationError";
  }
}

/**
 * A provider returned output that failed the step schema. Deterministic:
 * retrying the same prompt on the same provider would repeat it, so the
 * chain moves to the next candidate immediately.
 */
export class SchemaRejectionError extends WorkflowError {
  constructor(message: string) {
    super(message);
    this.name = "SchemaRejectionError";
  }
}

/** Timeout, connection failure, 429/5xx — plausibly succeeds on retry. */
export class TransientProviderError extends WorkflowError {
  constructor(message: string) {
    super(message);
    this.name = "TransientProviderError";
  }
}

/** Every candidate in the chain failed; carries the per-tier attempts. */
export class ProviderChainExhaustedError extends WorkflowError {
  readonly attempts: readonly AttemptOutcome[];
  constructor(message: string, attempts: readonly AttemptOutcome[]) {
    super(message);
    this.name = "ProviderChainExhaustedError";
    this.attempts = attempts;
  }
}

export interface AttemptOutcome {
  readonly tier: ProviderTier;
  readonly model: string;
  readonly outcome: "ok" | "failed" | "schema_rejected" | "retries_exhausted";
  readonly error?: string;
}

export type ProviderTier = "local" | "openrouter" | "nebius";

/** One recorded provider attempt, for run receipts and traces. */
export interface AttemptRecord {
  readonly name: string;
  readonly tier: ProviderTier;
  readonly model: string;
  readonly outcome: "ok" | "failed" | "schema_rejected" | "retries_exhausted";
  readonly error?: string;
}

/**
 * Classify a raw provider error as transient (retryable on the same
 * candidate) or fatal (move on). Never retries schema rejections — a
 * deterministic rejection just repeats.
 */
export function classifyProviderError(error: unknown): "transient" | "fatal" | "schema" {
  if (error instanceof SchemaRejectionError) return "schema";
  if (error instanceof TransientProviderError) return "transient";
  const message = error instanceof Error ? error.message : String(error);
  const transientPatterns = [
    /timeout/i,
    /timed out/i,
    /econnrefused/i,
    /econnreset/i,
    /etimedout/i,
    /socket hang up/i,
    /rate limit/i,
    /\b429\b/,
    /\b5\d{2}\b/,
    /status code 5\d{2}/i,
  ];
  return transientPatterns.some((pattern) => pattern.test(message)) ? "transient" : "fatal";
}
