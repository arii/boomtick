import { CallToolResult } from "@modelcontextprotocol/sdk/types.js";

export interface ToolResult extends CallToolResult {
  isError?: boolean;
}

export function createSuccessResult(data: any): ToolResult {
  const structuredContent =
    typeof data === "object" && data !== null
      ? data
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
