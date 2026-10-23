import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { createMcpHttpServer } from "./http.js";
import { BoomtickMCPServer } from "./server.js";

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

  it("should respond with RFC 9728 OAuth protected resource metadata on /.well-known/oauth-protected-resource", async () => {
    httpServerObj = createMcpHttpServer({ port: 0, mcpServer });
    port = await httpServerObj.listen(0);

    const res = await fetch(`http://localhost:${port}/.well-known/oauth-protected-resource`);
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toContain("application/json");

    const body = await res.json();
    expect(body.resource).toBe("mcp://boomtick-mcp");
    expect(body.authorization_servers).toEqual(["https://auth.boomtick.dev"]);
    expect(body.scopes_supported).toEqual(["mcp:read", "mcp:write"]);
    expect(body.bearer_methods_supported).toEqual(["header"]);
    expect(body.resource_documentation).toBe("https://github.com/arii/boomtick");
  });

  it("should handle HEAD requests for /.well-known/oauth-protected-resource", async () => {
    httpServerObj = createMcpHttpServer({ port: 0, mcpServer });
    port = await httpServerObj.listen(0);

    const res = await fetch(`http://localhost:${port}/.well-known/oauth-protected-resource`, {
      method: "HEAD",
    });
    expect(res.status).toBe(200);
    const text = await res.text();
    expect(text).toBe("");
  });

  it("should handle OPTIONS preflight CORS requests", async () => {
    httpServerObj = createMcpHttpServer({ port: 0, mcpServer });
    port = await httpServerObj.listen(0);

    const res = await fetch(`http://localhost:${port}/sse`, {
      method: "OPTIONS",
    });
    expect(res.status).toBe(204);
    expect(res.headers.get("access-control-allow-origin")).toBe("*");
    expect(res.headers.get("access-control-allow-methods")).toContain("GET");
    expect(res.headers.get("access-control-allow-headers")).toContain("Authorization");
  });

  it("should reject protected requests when Bearer token is missing or invalid", async () => {
    httpServerObj = createMcpHttpServer({ port: 0, bearerToken: "secret123", mcpServer });
    port = await httpServerObj.listen(0);

    // Request without token
    const res1 = await fetch(`http://localhost:${port}/sse`);
    expect(res1.status).toBe(401);
    expect(res1.headers.get("www-authenticate")).toContain('Bearer realm="boomtick-mcp"');
    expect(res1.headers.get("www-authenticate")).toContain('error="invalid_token"');

    // Request with wrong token
    const res2 = await fetch(`http://localhost:${port}/sse`, {
      headers: { Authorization: "Bearer wrong" },
    });
    expect(res2.status).toBe(401);

    // Public resource metadata accessible with or without token
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

  it("should return 500 if bearer token is not configured on server for protected endpoints", async () => {
    httpServerObj = createMcpHttpServer({ port: 0, mcpServer });
    port = await httpServerObj.listen(0);

    const res = await fetch(`http://localhost:${port}/sse`);
    expect(res.status).toBe(500);
    const body = await res.json();
    expect(body.error).toContain("Server misconfiguration");
  });

  it("should return 400 for message requests without session or invalid session", async () => {
    httpServerObj = createMcpHttpServer({ port: 0, bearerToken: "secret123", mcpServer });
    port = await httpServerObj.listen(0);

    const res = await fetch(`http://localhost:${port}/messages?sessionId=invalid_session`, {
      method: "POST",
      headers: {
        Authorization: "Bearer secret123",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ jsonrpc: "2.0", method: "ping", id: 1 }),
    });

    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toContain("Session not found or expired");
  });

  it("should allow BoomtickMCPServer to start HTTP server via startHttp()", async () => {
    const boomtickServer = new BoomtickMCPServer();
    const serverPort = await boomtickServer.startHttp(0, "test-token");
    expect(serverPort).toBeGreaterThan(0);

    const res = await fetch(`http://localhost:${serverPort}/.well-known/oauth-protected-resource`);
    expect(res.status).toBe(200);
  });
});
