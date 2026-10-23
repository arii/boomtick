#!/usr/bin/env node
import { BoomtickMCPServer } from "./mcp/server.js";
import { initializeConfig } from "./config.js";

initializeConfig();

let port = parseInt(process.env.PORT || process.env.HTTP_PORT || "3000", 10);
let bearerToken = process.env.BOOMTICK_MCP_BEARER_TOKEN || process.env.MCP_BEARER_TOKEN || process.env.AUTH_TOKEN;

const args = process.argv.slice(2);
for (let i = 0; i < args.length; i++) {
  if (args[i] === "--port" && i + 1 < args.length) {
    port = parseInt(args[i + 1], 10);
    i++;
  } else if (args[i].startsWith("--port=")) {
    port = parseInt(args[i].split("=")[1], 10);
  } else if (args[i] === "--bearer-token" && i + 1 < args.length) {
    bearerToken = args[i + 1];
    i++;
  } else if (args[i].startsWith("--bearer-token=")) {
    bearerToken = args[i].split("=")[1];
  }
}

const server = new BoomtickMCPServer();
server.startHttp(port, bearerToken).catch((error) => {
  console.error("Fatal error running HTTP server:", error);
  process.exit(1);
});
