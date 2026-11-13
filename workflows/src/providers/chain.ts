import { classifyProviderError, ProviderTier, ProviderChainExhaustedError, AttemptRecord } from "../errors.js";

/**
 * A structured-output candidate: one provider already wrapped so that
 * invoke() returns schema-conformant data (or throws). The provider chain
 * is composed over wrapped candidates — never over raw chat models — so
 * every fallback returns the same typed output.
 */
export interface StructuredCandidate<T> {
  readonly tier: ProviderTier;
  readonly model: string;
  readonly invoke: (input: string) => Promise<T>;
}

export interface StructuredCallResult<T> {
  readonly value: T;
  readonly tier: ProviderTier;
  readonly model: string;
  readonly attempts: readonly AttemptRecord[];
}

export interface StructuredChainOptions<T> {
  /** Candidates in failover order: local first, then cloud tiers. */
  candidates: readonly StructuredCandidate<T>[];
  /** Final gate: re-validate candidate output with the step's Zod schema. */
  validate: (value: unknown) => T;
  /** Transient-error retries per candidate (default 2, per the runtime research). */
  maxTransientRetries?: number;
  /** Backoff between transient retries; injectable so tests stay fast. */
  sleep?: (ms: number) => Promise<void>;
  /** Base backoff in ms for transient retries (default 500). */
  backoffMs?: number;
}

const defaultSleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

/** Per-candidate attempt outcome: a validated value, or a recorded failure. */
type CandidateOutcome<T> = { ok: true; value: T } | { ok: false };

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * Compose the provider chain over schema-wrapped candidates. Within a
 * candidate: transient errors retry (with backoff); schema rejections and
 * fatal errors move to the next candidate immediately. Across candidates:
 * strictly in order, and the receipt records every attempt so traces show
 * which tier answered.
 */
export function createStructuredChain<T>(options: StructuredChainOptions<T>): {
  run: (input: string) => Promise<StructuredCallResult<T>>;
} {
  const maxRetries = options.maxTransientRetries ?? 2;
  const sleep = options.sleep ?? defaultSleep;
  const backoffMs = options.backoffMs ?? 500;

  const record = (candidate: StructuredCandidate<T>, outcome: AttemptRecord["outcome"], error?: unknown): AttemptRecord => ({
    name: candidate.tier,
    tier: candidate.tier,
    model: candidate.model,
    outcome,
    ...(error !== undefined ? { error: errorMessage(error) } : {}),
  });

  const runCandidate = async (
    candidate: StructuredCandidate<T>,
    input: string,
    attempts: AttemptRecord[],
  ): Promise<CandidateOutcome<T>> => {
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        const raw = await candidate.invoke(input);
        const value = options.validate(raw);
        attempts.push(record(candidate, "ok"));
        return { ok: true, value };
      } catch (error) {
        const kind = classifyProviderError(error);
        // A deterministic schema rejection just repeats — never retry it.
        if (kind === "schema") {
          attempts.push(record(candidate, "schema_rejected", error));
          return { ok: false };
        }
        if (kind === "transient" && attempt < maxRetries) {
          await sleep(backoffMs * 2 ** attempt);
          continue;
        }
        attempts.push(record(candidate, kind === "transient" ? "retries_exhausted" : "failed", error));
        return { ok: false };
      }
    }
    return { ok: false };
  };

  return {
    async run(input: string): Promise<StructuredCallResult<T>> {
      const attempts: AttemptRecord[] = [];

      for (const candidate of options.candidates) {
        const outcome = await runCandidate(candidate, input, attempts);
        if (outcome.ok) {
          return { value: outcome.value, tier: candidate.tier, model: candidate.model, attempts };
        }
      }

      throw new ProviderChainExhaustedError(
        `All provider tiers failed for this step (${attempts.length} attempts recorded).`,
        attempts,
      );
    },
  };
}
