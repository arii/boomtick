import { RunWorkflowInput, RunWorkflowResponse } from "./contract.js";

// The workflows package owns the registry and the gateway; this handler is a
// thin MCP shim. The registry initializes lazily on first call so a bad
// provider env (e.g. OPENROUTER_API_KEY without OPENROUTER_MODEL) surfaces as
// a per-call tool error instead of crashing the whole server at startup.
type GatewayModule = typeof import("@arii/boomtick-workflows");
let gatewayPromise: Promise<{ runWorkflowGateway: GatewayModule["runWorkflowGateway"]; registry: InstanceType<GatewayModule["WorkflowRegistry"]> }> | undefined;

async function getGateway() {
  if (!gatewayPromise) {
    gatewayPromise = import("@arii/boomtick-workflows").then((module) => ({
      runWorkflowGateway: module.runWorkflowGateway,
      registry: module.createDefaultRegistry(),
    }));
  }
  return gatewayPromise;
}

/** Registry descriptor for the boomtick://workflows/registry resource. */
export async function describeWorkflowRegistry(): Promise<unknown> {
  const { registry } = await getGateway();
  return registry.describe();
}

export async function runWorkflowHandler(input: RunWorkflowInput): Promise<RunWorkflowResponse> {
  const { runWorkflowGateway, registry } = await getGateway();
  try {
    const receipt = await runWorkflowGateway(input, { registry });
    return {
      message: null,
      code: null,
      status: receipt.status,
      workflow: receipt.workflow ?? null,
      result: receipt.result ?? null,
      steps: receipt.steps.map((step) => ({
        name: step.name,
        status: step.outcome,
        tier: step.tier,
        model: step.model,
        error: step.error ?? null,
      })),
      tier: receipt.tier ?? null,
      model: receipt.model ?? null,
      error: receipt.error ?? null,
    };
  } catch (error) {
    // Validation errors are deterministic rejections: report them as a
    // receipt, not an exception, so agents get actionable text back.
    return {
      message: null,
      code: null,
      status: "error",
      workflow: input.workflow ?? null,
      result: null,
      steps: [],
      tier: null,
      model: null,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}
