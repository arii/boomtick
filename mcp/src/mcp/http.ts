import http from "node:http";
import crypto from "node:crypto";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { SSEServerTransport } from "@modelcontextprotocol/sdk/server/sse.js";

export interface HttpServerOptions {
  port?: number;
  bearerToken?: string;
  mcpServer: Server;
}

export function createMcpHttpServer(options: HttpServerOptions) {
  const {
    port = 3000,
    bearerToken = process.env.BOOMTICK_MCP_BEARER_TOKEN || process.env.MCP_BEARER_TOKEN || process.env.AUTH_TOKEN,
    mcpServer,
  } = options;

  const transports = new Map<string, SSEServerTransport>();

  const server = http.createServer(async (req, res) => {
    // CORS Headers
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS, HEAD");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization");

    if (req.method === "OPTIONS") {
      res.writeHead(204);
      res.end();
      return;
    }

    const url = new URL(req.url || "/", `http://${req.headers.host || "localhost"}`);

    // Endpoint 1: RFC 9728 OAuth Protected Resource Metadata Discovery
    if (url.pathname === "/.well-known/oauth-protected-resource" && (req.method === "GET" || req.method === "HEAD")) {
      const metadata = {
        resource: process.env.MCP_RESOURCE_URI || process.env.BOOMTICK_RESOURCE_URI || "mcp://boomtick-mcp",
        authorization_servers: [
          process.env.MCP_OAUTH_AUTH_SERVER || "https://auth.boomtick.dev",
        ],
        scopes_supported: ["mcp:read", "mcp:write"],
        bearer_methods_supported: ["header"],
        resource_documentation: process.env.MCP_RESOURCE_DOCS || "https://github.com/arii/boomtick",
      };

      res.writeHead(200, { "Content-Type": "application/json" });
      if (req.method === "HEAD") {
        res.end();
      } else {
        res.end(JSON.stringify(metadata, null, 2));
      }
      return;
    }

    // Bearer Token / OAuth 2.1 Validation for Protected Routes (/sse & /messages)
    if (url.pathname === "/sse" || url.pathname === "/messages") {
      if (!bearerToken) {
        res.writeHead(500, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "Server misconfiguration: bearerToken is required for HTTP transport" }));
        return;
      }

      const authHeader = req.headers.authorization;
      const expectedAuth = `Bearer ${bearerToken}`;
      const authBuffer = Buffer.from(authHeader || "");
      const expectedBuffer = Buffer.from(expectedAuth);
      const isMatch =
        Boolean(authHeader) &&
        authBuffer.length === expectedBuffer.length &&
        crypto.timingSafeEqual(authBuffer, expectedBuffer);

      if (!isMatch) {
        res.writeHead(401, {
          "Content-Type": "application/json",
          "WWW-Authenticate": 'Bearer realm="boomtick-mcp", error="invalid_token", error_description="Invalid or missing Bearer token"',
        });
        res.end(JSON.stringify({ error: "unauthorized", message: "Invalid or missing Bearer token" }));
        return;
      }
    }

    // Endpoint 2: SSE stream setup
    if (url.pathname === "/sse" && req.method === "GET") {
      const transport = new SSEServerTransport("/messages", res);
      transports.set(transport.sessionId, transport);
      transport.onclose = () => {
        transports.delete(transport.sessionId);
      };
      await mcpServer.connect(transport);
      return;
    }

    // Endpoint 3: POST messages
    if (url.pathname === "/messages" && req.method === "POST") {
      const sessionId = url.searchParams.get("sessionId");
      const transport = sessionId ? transports.get(sessionId) : null;
      if (transport) {
        await transport.handlePostMessage(req, res);
      } else {
        res.writeHead(400, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "Session not found or expired" }));
      }
      return;
    }

    res.writeHead(404, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "Not found" }));
  });

  return {
    server,
    listen: (customPort?: number) =>
      new Promise<number>((resolve) => {
        const p = customPort ?? port;
        server.listen(p, () => {
          const addr = server.address();
          const actualPort = typeof addr === "object" && addr ? addr.port : p;
          console.error(`Boomtick MCP Server running on HTTP port ${actualPort}`);
          resolve(actualPort);
        });
      }),
  };
}
