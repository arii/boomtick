import { CallToolResult } from "@modelcontextprotocol/sdk/types.js";

export interface ToolResult extends CallToolResult {
  isError?: boolean;
}

export function createSuccessResult(data: unknown): ToolResult {
  const structuredContent: Record<string, unknown> =
    typeof data === "object" && data !== null && !Array.isArray(data)
      ? (data as Record<string, unknown>)
      : { result: data };

  return {
    content: [
      {
        type: "text",
        text: typeof data === "string" ? data : JSON.stringify(data, null, 2),
      },
    ],
    structuredContent,
  };
}

export function createErrorResult(message: string): ToolResult {
  return {
    content: [
      {
        type: "text",
        text: message,
      },
    ],
    isError: true,
  };
}
