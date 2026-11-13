import { z } from "zod";
import { WorkflowValidationError } from "./errors.js";
import { WorkflowStateType } from "./state.js";

/**
 * The only graph surface the registry and gateway rely on: invoke with the
 * validated input and await the final state. Kept structural because
 * CompiledStateGraph's generics are node-set dependent and would leak graph
 * internals into every workflow's signature; concrete workflows still build
 * through StateGraph over WorkflowState.
 */
export interface InvocableWorkflowGraph {
  invoke(input: { input: Record<string, unknown> }): Promise<WorkflowStateType>;
}

/**
 * A registered workflow: a fixed LangGraph graph plus the Zod schema the
 * gateway enforces on its input. Nothing here is autonomous — the graph's
 * shape is the contract.
 */
export interface WorkflowDefinition {
  readonly id: string;
  readonly description: string;
  readonly inputSchema: z.ZodType;
  readonly graph: InvocableWorkflowGraph;
}

const workflowIdPattern = /^[a-z][a-z0-9_]{1,63}$/;

export class WorkflowRegistry {
  private readonly workflows = new Map<string, WorkflowDefinition>();

  register(definition: WorkflowDefinition): void {
    if (!workflowIdPattern.test(definition.id)) {
      throw new WorkflowValidationError(
        `Workflow id "${definition.id}" violates the registry pattern ${workflowIdPattern.source} — ids become MCP request fields and resource keys, so they stay lowercase snake_case.`,
      );
    }
    if (this.workflows.has(definition.id)) {
      throw new WorkflowValidationError(`Workflow id "${definition.id}" is already registered.`);
    }
    this.workflows.set(definition.id, definition);
  }

  require(id: string): WorkflowDefinition {
    const definition = this.workflows.get(id);
    if (!definition) {
      throw new WorkflowValidationError(
        `Unknown workflow: "${id}". Registered workflows: ${[...this.workflows.keys()].join(", ") || "(none)"}. See the boomtick://workflows/registry resource for input schemas.`,
      );
    }
    return definition;
  }

  list(): WorkflowDefinition[] {
    return [...this.workflows.values()];
  }

  /** Registry descriptor for the boomtick://workflows/registry resource. */
  describe(): { workflows: Array<{ id: string; description: string; inputSchema: unknown }> } {
    return {
      workflows: this.list().map((definition) => ({
        id: definition.id,
        description: definition.description,
        // zod v4 ships a first-class JSON Schema converter; the registry is
        // the single place wire schemas are derived from the runtime Zod.
        inputSchema: z.toJSONSchema(definition.inputSchema),
      })),
    };
  }
}

/**
 * Validate raw workflow input against the registered per-workflow schema.
 * Shared issue formatting lives here so gateway and per-workflow rejections
 * read identically.
 */
export function formatZodIssues(error: z.ZodError): string {
  return error.issues.map((issue) => `${issue.path.join(".") || "(root)"}: ${issue.message}`).join("; ");
}

/** Validate raw workflow input against the registered per-workflow schema. */
export function validateWorkflowInput<T>(definition: WorkflowDefinition, input: unknown): T {
  const parsed = definition.inputSchema.safeParse(input ?? {});
  if (!parsed.success) {
    throw new WorkflowValidationError(`Input rejected for workflow "${definition.id}" — ${formatZodIssues(parsed.error)}`);
  }
  return parsed.data as T;
}

/** Invoke a registered workflow graph and return its final state. */
export async function invokeWorkflow(
  definition: WorkflowDefinition,
  input: Record<string, unknown>,
): Promise<WorkflowStateType> {
  return definition.graph.invoke({ input });
}
