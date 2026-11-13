import { WorkflowRegistry } from "./registry.js";
import { createEchoWorkflow } from "./workflows/echo.js";
import { createStructuredExtractWorkflow } from "./workflows/structured_extract.js";
import { readProviderEnv } from "./providers/config.js";

/**
 * Default registry with the shipped workflow set. Cloud candidates activate
 * only when OPENROUTER_API_KEY/OPENROUTER_MODEL or NEBIUS_API_KEY/NEBIUS_MODEL
 * are set; without them the chain degrades to local-only.
 */
export function createDefaultRegistry(): WorkflowRegistry {
  const registry = new WorkflowRegistry();
  registry.register(createEchoWorkflow());
  registry.register(createStructuredExtractWorkflow(readProviderEnv()));
  return registry;
}

export { WorkflowRegistry, WorkflowDefinition, invokeWorkflow, validateWorkflowInput } from "./registry.js";
export { runWorkflowGateway, RunWorkflowReceipt } from "./gateway.js";
export { createStructuredChain, StructuredCandidate, StructuredCallResult } from "./providers/chain.js";
export {
  readProviderEnv,
  ProviderEnvConfig,
  configuredTiers,
  DEFAULT_LOCAL_STRUCTURED_MODEL,
  DEFAULT_LOCAL_TOOL_MODEL,
  WORKFLOW_TEMPERATURE,
  LOCAL_NUM_CTX,
} from "./providers/config.js";
export {
  WorkflowError,
  WorkflowValidationError,
  SchemaRejectionError,
  TransientProviderError,
  ProviderChainExhaustedError,
  classifyProviderError,
  ProviderTier,
} from "./errors.js";
export { WorkflowState, WorkflowStateType } from "./state.js";
export { createStdioMcpClient, McpToolClient } from "./mcpClient.js";
