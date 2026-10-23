#!/usr/bin/env node
import { BoomtickMCPServer } from "./mcp/server.js";
import { initializeConfig } from "./config.js";

initializeConfig();

process.env.MCP_TRANSPORT = "http";

const server = new BoomtickMCPServer();
server.run().catch((error) => {
  console.error("Fatal error running HTTP server:", error);
  process.exit(1);
});
