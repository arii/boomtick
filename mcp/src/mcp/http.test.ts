import { describe, it, expect, beforeEach, afterEach } from "vitest";
import http from "node:http";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { createMcpHttpServer } from "./http.js";

describe("createMcpHttpServer", () => {
  let mcpServer: Server;
  let httpServerObj: ReturnType<typeof createMcpHttpServer>;
  let port: number;

  beforeEach(async () => {
    mcpServer = new Server({ name: "test-server", version: "1.0.0" }, { capabilities: {} });
  });

  afterEach(() => {
    if (httpServerObj?.server) {
      httpServerObj.server.close();
    }
  });

  it("should respond with OAuth protected resource metadata on /.well-known/oauth-protected-resource", async () => {
    httpServerObj = createMcpHttpServer({ port: 0, mcpServer });
    port = await httpServerObj.listen(0);

    const res = await fetch(`http://localhost:${port}/.well-known/oauth-protected-resource`);
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.resource).toBe("mcp://boomtick-mcp");
    expect(body.authorization_servers).toBeDefined();
    expect(body.scopes_supported).toEqual(["mcp:read", "mcp:write"]);
  });

  it("should reject requests when Bearer token is missing or invalid", async () => {
    httpServerObj = createMcpHttpServer({ port: 0, bearerToken: "secret123", mcpServer });
    port = await httpServerObj.listen(0);

    // Request without token
    const res1 = await fetch(`http://localhost:${port}/sse`);
    expect(res1.status).toBe(401);
    expect(res1.headers.get("www-authenticate")).toContain('Bearer realm="boomtick-mcp"');

    // Request with wrong token
    const res2 = await fetch(`http://localhost:${port}/sse`, {
      headers: { Authorization: "Bearer wrong" },
    });
    expect(res2.status).toBe(401);

    // Request with valid token
    const res3 = await fetch(`http://localhost:${port}/.well-known/oauth-protected-resource`, {
      headers: { Authorization: "Bearer secret123" },
    });
    expect(res3.status).toBe(200);
  });

  it("should handle 404 for unknown endpoints", async () => {
    httpServerObj = createMcpHttpServer({ port: 0, mcpServer });
    port = await httpServerObj.listen(0);

    const res = await fetch(`http://localhost:${port}/unknown-path`);
    expect(res.status).toBe(404);
  });
});
