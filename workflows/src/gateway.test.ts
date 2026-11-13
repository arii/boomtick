import { describe, expect, it } from "vitest";
import { runWorkflowGateway, GatewayDeps } from "./gateway.js";
import { WorkflowRegistry } from "./registry.js";
import { createEchoWorkflow } from "./workflows/echo.js";
import {
  createStructuredExtractWorkflow,
  StructuredExtractDeps,
  StructuredExtractOutput,
} from "./workflows/structured_extract.js";
import { ProviderEnvConfig } from "./providers/config.js";
import { StructuredCandidate } from "./providers/chain.js";
import { TransientProviderError, WorkflowValidationError } from "./errors.js";

const noSleep = async () => undefined;

function fakeCandidate(
  tier: StructuredCandidate<StructuredExtractOutput>["tier"],
  behavior: () => Promise<StructuredExtractOutput>,
): StructuredCandidate<StructuredExtractOutput> {
  return { tier, model: `mock-${tier}`, invoke: behavior };
}

const localConfig: ProviderEnvConfig = {
  ollamaBaseUrl: "http://127.0.0.1:11434",
  localStructuredModel: "gemma3:4b",
  localToolModel: "phi4-mini",
};

function registryWithExtract(deps: StructuredExtractDeps = {}): WorkflowRegistry {
  const registry = new WorkflowRegistry();
  registry.register(createEchoWorkflow());
  registry.register(createStructuredExtractWorkflow(localConfig, { sleep: noSleep, ...deps }));
  return registry;
}

describe("run_workflow gateway: request validation", () => {
  const deps: GatewayDeps = { registry: registryWithExtract() };

  it("rejects a non-object request", async () => {
    await expect(runWorkflowGateway("echo", deps)).rejects.toThrow(WorkflowValidationError);
    await expect(runWorkflowGateway(null, deps)).rejects.toThrow(/Malformed run_workflow request/);
  });

  it("rejects a missing workflow id", async () => {
    await expect(runWorkflowGateway({ input: {} }, deps)).rejects.toThrow(
      /Malformed run_workflow request — workflow: Invalid input: expected string/,
    );
  });

  it("rejects unknown workflow ids deterministically, naming the registry", async () => {
    await expect(runWorkflowGateway({ workflow: "totally_unknown" }, deps)).rejects.toThrow(
      /Unknown workflow: "totally_unknown". Registered workflows: echo, structured_extract/,
    );
  });

  it("rejects input that fails the per-workflow schema", async () => {
    await expect(runWorkflowGateway({ workflow: "echo", input: { repeat: 2 } }, deps)).rejects.toThrow(
      /Input rejected for workflow "echo" — message:/,
    );
  });
});

describe("run_workflow gateway: end-to-end over the stub path", () => {
  const deps: GatewayDeps = { registry: registryWithExtract() };

  it("runs the echo workflow to completion with a tiered receipt", async () => {
    const receipt = await runWorkflowGateway(
      { workflow: "echo", input: { message: "hello world", repeat: 3 } },
      deps,
    );
    expect(receipt.status).toBe("success");
    expect(receipt.workflow).toBe("echo");
    expect(receipt.result).toEqual({ echoed: "hello world", repeat: 3 });
    expect(receipt.steps).toEqual([
      { name: "echo", tier: "local", model: "deterministic", outcome: "ok" },
    ]);
  });

  it("treats omitted input as an empty object (echo still requires its field)", async () => {
    await expect(runWorkflowGateway({ workflow: "echo" }, deps)).rejects.toThrow(/message:/);
  });
});

describe("run_workflow gateway: structured_extract with mocked providers", () => {
  it("records the answering tier in the receipt on success", async () => {
    const deps: GatewayDeps = {
      registry: registryWithExtract({
        candidates: [fakeCandidate("local", async () => ({ summary: "s", tags: ["t"] }))],
      }),
    };
    const receipt = await runWorkflowGateway({ workflow: "structured_extract", input: { text: "hello" } }, deps);
    expect(receipt.status).toBe("success");
    expect(receipt.tier).toBe("local");
    expect(receipt.model).toBe("mock-local");
    expect(receipt.result).toEqual({ summary: "s", tags: ["t"] });
  });

  it("falls back to the cloud tier when local is unreachable, receipt shows the chain", async () => {
    const deps: GatewayDeps = {
      registry: registryWithExtract({
        candidates: [
          fakeCandidate("local", async () => {
            throw new TransientProviderError("ECONNREFUSED 127.0.0.1:11434");
          }),
          fakeCandidate("openrouter", async () => ({ summary: "cloud", tags: [] })),
        ],
      }),
    };
    const receipt = await runWorkflowGateway({ workflow: "structured_extract", input: { text: "hello" } }, deps);
    expect(receipt.status).toBe("success");
    expect(receipt.tier).toBe("openrouter");
    expect(receipt.steps.map((step) => step.tier)).toEqual(["local", "openrouter"]);
  });

  it("returns an error receipt with attempts after the chain is exhausted", async () => {
    const deps: GatewayDeps = {
      registry: registryWithExtract({
        candidates: [
          fakeCandidate("local", async () => {
            throw new TransientProviderError("ECONNREFUSED 127.0.0.1:11434");
          }),
          fakeCandidate("nebius", async () => {
            throw new TransientProviderError("status code 429: quota exhausted");
          }),
        ],
      }),
    };
    const receipt = await runWorkflowGateway({ workflow: "structured_extract", input: { text: "hello" } }, deps);
    expect(receipt.status).toBe("error");
    expect(receipt.error).toMatch(/chain was exhausted/);
    // Both graph nodes (extract, repair) exhaust the two-tier chain: 2
    // retries_exhausted records per node, attempts preserved in the receipt.
    expect(receipt.steps.map((step) => step.outcome)).toEqual([
      "retries_exhausted",
      "retries_exhausted",
      "retries_exhausted",
      "retries_exhausted",
    ]);
  });

  it("gives the model exactly one repair attempt on a schema rejection", async () => {
    let calls = 0;
    const deps: GatewayDeps = {
      registry: registryWithExtract({
        candidates: [
          fakeCandidate("local", async () => {
            calls++;
            if (calls === 1) {
              return { summary: 12345 } as unknown as StructuredExtractOutput; // malformed
            }
            return { summary: "repaired", tags: [] };
          }),
        ],
      }),
    };
    const receipt = await runWorkflowGateway({ workflow: "structured_extract", input: { text: "hello" } }, deps);
    expect(calls).toBe(2);
    expect(receipt.status).toBe("success");
    expect(receipt.result).toEqual({ summary: "repaired", tags: [] });
  });

  it("fails after the single repair attempt, never looping", async () => {
    let calls = 0;
    const deps: GatewayDeps = {
      registry: registryWithExtract({
        candidates: [
          fakeCandidate("local", async () => {
            calls++;
            return { summary: 12345 } as unknown as StructuredExtractOutput; // always malformed
          }),
        ],
      }),
    };
    const receipt = await runWorkflowGateway({ workflow: "structured_extract", input: { text: "hello" } }, deps);
    expect(calls).toBe(2); // extract + one repair
    expect(receipt.status).toBe("error");
    expect(receipt.error).toMatch(/repair attempt failed/);
  });

  it("clamps runaway tag lists from small models", async () => {
    const tags = Array.from({ length: 20 }, (_, i) => `tag${i}`);
    const deps: GatewayDeps = {
      registry: registryWithExtract({
        candidates: [fakeCandidate("local", async () => ({ summary: "s", tags }))],
      }),
    };
    const receipt = await runWorkflowGateway({ workflow: "structured_extract", input: { text: "hello" } }, deps);
    expect((receipt.result as { tags: string[] }).tags).toHaveLength(5);
  });
});
