import { describe, expect, it } from "vitest";
import { z } from "zod";
import { WorkflowRegistry, validateWorkflowInput } from "./registry.js";
import { createEchoWorkflow } from "./workflows/echo.js";
import { invokeWorkflow } from "./registry.js";

describe("WorkflowRegistry", () => {
  it("registers and lists workflows by id", () => {
    const registry = new WorkflowRegistry();
    registry.register(createEchoWorkflow());
    expect(registry.list().map((w) => w.id)).toEqual(["echo"]);
    expect(registry.require("echo").id).toBe("echo");
  });

  it("rejects unknown ids deterministically, naming the registered set", () => {
    const registry = new WorkflowRegistry();
    registry.register(createEchoWorkflow());
    expect(() => registry.require("no_such_workflow")).toThrow(
      /Unknown workflow: "no_such_workflow". Registered workflows: echo/,
    );
  });

  it("rejects duplicate ids and malformed id patterns", () => {
    const registry = new WorkflowRegistry();
    registry.register(createEchoWorkflow());
    expect(() => registry.register(createEchoWorkflow())).toThrow(/already registered/);

    const bad = { ...createEchoWorkflow(), id: "Bad-Id.Dot" };
    expect(() => registry.register(bad)).toThrow(/violates the registry pattern/);
  });

  it("describes the registry with per-workflow JSON input schemas", () => {
    const registry = new WorkflowRegistry();
    registry.register(createEchoWorkflow());
    const descriptor = registry.describe();
    expect(descriptor.workflows).toHaveLength(1);
    const schema = descriptor.workflows[0].inputSchema as { properties: Record<string, unknown> };
    expect(schema.properties.message).toBeDefined();
  });
});

describe("validateWorkflowInput", () => {
  it("passes schema-conformant input through", () => {
    const definition = createEchoWorkflow();
    const input = validateWorkflowInput<{ message: string }>(definition, { message: "hello" });
    expect(input.message).toBe("hello");
  });

  it("rejects malformed input with field-level errors", () => {
    const definition = createEchoWorkflow();
    expect(() => validateWorkflowInput(definition, { repeat: 3 })).toThrow(
      /Input rejected for workflow "echo" — message: /,
    );
    expect(() => validateWorkflowInput(definition, { message: "x", repeat: 99 })).toThrow(/repeat/);
  });
});

describe("invokeWorkflow (echo graph)", () => {
  it("runs the fixed graph and writes result + step receipt", async () => {
    const definition = createEchoWorkflow();
    const state = await invokeWorkflow(definition, { message: "hello", repeat: 2 });
    expect(state.result).toEqual({ echoed: "hello", repeat: 2 });
    expect(state.steps).toEqual([
      { name: "echo", tier: "local", model: "deterministic", outcome: "ok" },
    ]);
    expect(state.error).toBeUndefined();
  });

  it("defaults repeat to 1 via the Zod schema default", async () => {
    const definition = createEchoWorkflow();
    const input = validateWorkflowInput<{ message: string; repeat?: number }>(definition, { message: "hi" });
    const state = await invokeWorkflow(definition, input as unknown as Record<string, unknown>);
    expect(state.result).toEqual({ echoed: "hi", repeat: 1 });
  });

  it("is usable as a typed zod schema shape", () => {
    const schema: z.ZodType = createEchoWorkflow().inputSchema;
    expect(schema.safeParse({ message: "ok" }).success).toBe(true);
  });
});
