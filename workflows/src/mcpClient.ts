import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

/**
 * Minimal tool-calling surface over a stdio MCP child process. Workflows use
 * this to reach the boomtick MCP server's deterministic tools without an
 * HTTP hop — the server is local, trusted, and low-traffic, which is exactly
 * the case stdio wins (research art_7FsLzVOd §1).
 */
export interface McpToolClient {
  callTool(name: string, args: Record<string, unknown>): Promise<unknown>;
  close(): Promise<void>;
}

export interface StdioClientOptions {
  /** Server command, e.g. "boomtick-mcp" or ["node", "dist/index.js"]. */
  command: string;
  args?: string[];
  clientName?: string;
}

export async function createStdioMcpClient(options: StdioClientOptions): Promise<McpToolClient> {
  const transport = new StdioClientTransport({
    command: options.command,
    args: options.args ?? [],
  });
  const client = new Client({ name: options.clientName ?? "boomtick-workflows", version: "0.1.0" });
  await client.connect(transport);

  return {
    async callTool(name: string, args: Record<string, unknown>): Promise<unknown> {
      const result = await client.callTool({ name, arguments: args });
      if (result.isError) {
        const firstBlock = Array.isArray(result.content) ? result.content[0] : undefined;
        const text = firstBlock && "text" in firstBlock ? firstBlock.text : `tool ${name} failed`;
        throw new Error(`MCP tool ${name} returned an error: ${text}`);
      }
      return result;
    },
    close: () => client.close(),
  };
}
