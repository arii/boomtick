#!/usr/bin/env node
import { BoomtickMCPServer } from "./mcp/server.js";

const server = new BoomtickMCPServer();
server.run().catch((error) => {
  console.error("Fatal error running server:", error);
  process.exit(1);
});
