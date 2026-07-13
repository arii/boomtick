import { MCP_TOOLS, MCP_PROMPTS, MCP_RESOURCES } from "../src/mcp/definitions.js";

console.log(JSON.stringify({
  tools: MCP_TOOLS,
  prompts: MCP_PROMPTS,
  resources: MCP_RESOURCES
}, null, 2));
