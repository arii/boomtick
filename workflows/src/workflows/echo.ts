import { END, START, StateGraph } from "@langchain/langgraph";
import { z } from "zod";
import { WorkflowDefinition } from "../registry.js";
import { WorkflowState } from "../state.js";

const echoInputSchema = z.object({
  message: z.string().min(1).describe("Message to echo back."),
  repeat: z.number().int().min(1).max(10).optional().describe("Repeat count (default 1)."),
});

type EchoInput = z.infer<typeof echoInputSchema>;

/**
 * Stub workflow: fully deterministic, no provider calls. Exercises the
 * registry → gateway → graph path end to end so the gateway contract can be
 * verified without any model.
 */
export function createEchoWorkflow(): WorkflowDefinition {
  const graph = new StateGraph(WorkflowState)
    .addNode("echo", (state) => {
      const input = state.input as EchoInput;
      const repeat = input.repeat ?? 1;
      return {
        result: { echoed: input.message, repeat },
        steps: [{ name: "echo", tier: "local" as const, model: "deterministic", outcome: "ok" as const }],
      };
    })
    .addEdge(START, "echo")
    .addEdge("echo", END)
    .compile();

  return {
    id: "echo",
    description: "Deterministic stub: echoes its input back. No model calls; used to verify the gateway path.",
    inputSchema: echoInputSchema,
    graph,
  };
}
