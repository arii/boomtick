#!/usr/bin/env node
import { BoomtickMCPServer } from "./mcp/server.js";
import { initializeConfig } from "./config.js";

// Initialize configuration once at startup
initializeConfig();

const server = new BoomtickMCPServer();
server.run().catch((error) => {
  console.error("Fatal error running server:", error);
  process.exit(1);
});
