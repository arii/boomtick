import { describe, expect, it, vi } from "vitest";
import { SchemaRejectionError, TransientProviderError, classifyProviderError, ProviderChainExhaustedError } from "../errors.js";
import { createStructuredChain, StructuredCandidate } from "./chain.js";

interface FakeOutput {
  summary: string;
  tags: string[];
}

const validOutput: FakeOutput = { summary: "ok", tags: ["a"] };

function candidate(
  tier: string,
  model: string,
  behavior: () => Promise<FakeOutput>,
): StructuredCandidate<FakeOutput> {
  return {
    tier: tier as StructuredCandidate<FakeOutput>["tier"],
    model,
    invoke: behavior,
  };
}

const validate = (value: unknown): FakeOutput => {
  if (
    typeof value === "object" &&
    value !== null &&
    "summary" in value &&
    typeof (value as FakeOutput).summary === "string"
  ) {
    return value as FakeOutput;
  }
  throw new SchemaRejectionError("invalid shape");
};

const noSleep = async () => undefined;

describe("classifyProviderError", () => {
  it("classifies timeouts, 429s, and connection errors as transient", () => {
    expect(classifyProviderError(new Error("request timed out after 30s"))).toBe("transient");
    expect(classifyProviderError(new Error("status code 429: rate limited"))).toBe("transient");
    expect(classifyProviderError(new Error("connect ECONNREFUSED 127.0.0.1:11434"))).toBe("transient");
    expect(classifyProviderError(new Error("status code 502"))).toBe("transient");
  });

  it("classifies schema rejections as schema, other errors as fatal", () => {
    expect(classifyProviderError(new SchemaRejectionError("bad json"))).toBe("schema");
    expect(classifyProviderError(new Error("401 unauthorized"))).toBe("fatal");
  });
});

describe("createStructuredChain", () => {
  it("returns the first candidate's validated output with its tier", async () => {
    const chain = createStructuredChain<FakeOutput>({
      candidates: [candidate("local", "gemma3:4b", async () => validOutput)],
      validate,
      sleep: noSleep,
    });

    const result = await chain.run("prompt");
    expect(result.value).toEqual(validOutput);
    expect(result.tier).toBe("local");
    expect(result.model).toBe("gemma3:4b");
    expect(result.attempts).toHaveLength(1);
    expect(result.attempts[0].outcome).toBe("ok");
  });

  it("falls back to the next tier after transient retries are exhausted", async () => {
    const localInvoke = vi.fn(async () => {
      throw new TransientProviderError("ECONNREFUSED 127.0.0.1:11434");
    });
    const chain = createStructuredChain<FakeOutput>({
      candidates: [
        candidate("local", "gemma3:4b", localInvoke),
        candidate("openrouter", "test-free-model", async () => validOutput),
      ],
      validate,
      maxTransientRetries: 2,
      sleep: noSleep,
    });

    const result = await chain.run("prompt");
    expect(localInvoke).toHaveBeenCalledTimes(3); // 1 initial + 2 retries
    expect(result.tier).toBe("openrouter");
    expect(result.attempts.map((a) => a.outcome)).toEqual(["retries_exhausted", "ok"]);
  });

  it("never retries a schema rejection — moves to the next tier immediately", async () => {
    const localInvoke = vi.fn((async () => ({ wrong: "shape" })) as unknown as () => Promise<FakeOutput>);
    const chain = createStructuredChain<FakeOutput>({
      candidates: [
        candidate("local", "gemma3:4b", localInvoke),
        candidate("nebius", "test-model", async () => validOutput),
      ],
      validate,
      sleep: noSleep,
    });

    const result = await chain.run("prompt");
    expect(localInvoke).toHaveBeenCalledTimes(1);
    expect(result.tier).toBe("nebius");
    expect(result.attempts[0].outcome).toBe("schema_rejected");
  });

  it("re-validates candidate output with the step schema even if the provider lies", async () => {
    // Provider claims structured output but returns an unvalidated cast.
    const chain = createStructuredChain<FakeOutput>({
      candidates: [candidate("local", "gemma3:4b", async () => ({ summary: 42 }) as unknown as FakeOutput)],
      validate,
      sleep: noSleep,
    });

    await expect(chain.run("prompt")).rejects.toBeInstanceOf(ProviderChainExhaustedError);
  });

  it("throws ProviderChainExhaustedError carrying every attempt when all tiers fail", async () => {
    const chain = createStructuredChain<FakeOutput>({
      candidates: [
        candidate("local", "gemma3:4b", async () => {
          throw new Error("fatal auth failure");
        }),
        candidate("openrouter", "test-free-model", async () => {
          throw new SchemaRejectionError("malformed tool call");
        }),
      ],
      validate,
      sleep: noSleep,
    });

    try {
      await chain.run("prompt");
      expect.unreachable("chain should have thrown");
    } catch (error) {
      expect(error).toBeInstanceOf(ProviderChainExhaustedError);
      const exhausted = error as ProviderChainExhaustedError;
      expect(exhausted.attempts.map((a) => [a.tier, a.outcome])).toEqual([
        ["local", "failed"],
        ["openrouter", "schema_rejected"],
      ]);
    }
  });

  it("backs off exponentially between transient retries", async () => {
    const sleeps: number[] = [];
    let calls = 0;
    const chain = createStructuredChain<FakeOutput>({
      candidates: [
        candidate("local", "gemma3:4b", async () => {
          calls++;
          if (calls < 3) throw new TransientProviderError("timeout");
          return validOutput;
        }),
      ],
      validate,
      backoffMs: 100,
      sleep: async (ms) => {
        sleeps.push(ms);
      },
    });

    const result = await chain.run("prompt");
    expect(result.tier).toBe("local");
    expect(sleeps).toEqual([100, 200]);
  });
});
