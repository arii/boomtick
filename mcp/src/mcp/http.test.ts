import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import http from "node:http";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { SSEClientTransport } from "@modelcontextprotocol/sdk/client/sse.js";
import { SSEServerTransport } from "@modelcontextprotocol/sdk/server/sse.js";
import { createMcpHttpServer } from "./http.js";
import { BoomtickMCPServer } from "./server.js";

describe("createMcpHttpServer", () => {
  let createServer: () => Server;
  let httpServerObj: ReturnType<typeof createMcpHttpServer>;
  let port: number;

  beforeEach(async () => {
    createServer = () => new BoomtickMCPServer().createServer();
  });

  afterEach(() => {
    if (httpServerObj?.server) {
      httpServerObj.server.close();
    }
  });

  it("should respond with 200 on GET /health endpoint", async () => {
    httpServerObj = createMcpHttpServer({ port: 0, createServer });
    port = await httpServerObj.listen(0);

    const res = await fetch(`http://localhost:${port}/health`);
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body).toEqual({ status: "ok", transport: "http" });
  });

  it("should respond with RFC 9728 OAuth protected resource metadata on /.well-known/oauth-protected-resource", async () => {
    httpServerObj = createMcpHttpServer({ port: 0, createServer });
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
    httpServerObj = createMcpHttpServer({ port: 0, createServer });
    port = await httpServerObj.listen(0);

    const res = await fetch(`http://localhost:${port}/.well-known/oauth-protected-resource`, {
      method: "HEAD",
    });
    expect(res.status).toBe(200);
    const text = await res.text();
    expect(text).toBe("");
  });

  it("should handle OPTIONS preflight CORS requests", async () => {
    httpServerObj = createMcpHttpServer({ port: 0, createServer });
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
    httpServerObj = createMcpHttpServer({ port: 0, bearerToken: "secret123", createServer });
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
    httpServerObj = createMcpHttpServer({ port: 0, createServer });
    port = await httpServerObj.listen(0);

    const res = await fetch(`http://localhost:${port}/unknown-path`);
    expect(res.status).toBe(404);
  });

  it("should return 500 if bearer token is not configured on server for protected endpoints", async () => {
    httpServerObj = createMcpHttpServer({ port: 0, createServer });
    port = await httpServerObj.listen(0);

    const res = await fetch(`http://localhost:${port}/sse`);
    expect(res.status).toBe(500);
    const body = await res.json();
    expect(body.error).toContain("Server misconfiguration");
  });

  it("should return 400 for message requests without session or invalid session", async () => {
    httpServerObj = createMcpHttpServer({ port: 0, bearerToken: "secret123", createServer });
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

  it("audit H5: returns a JSON-RPC 500 error instead of crashing on a malformed Host header", async () => {
    httpServerObj = createMcpHttpServer({ port: 0, createServer });
    port = await httpServerObj.listen(0);

    // `new URL(req.url, "http://not a valid host")` throws on this request;
    // without the per-request catch that is an unhandled rejection (fatal on
    // Node 24). With the catch it must be a 500 JSON-RPC error response.
    const status = await new Promise<number>((resolve, reject) => {
      const req = http.request(
        { host: "127.0.0.1", port, path: "/health", method: "GET", headers: { Host: "not a valid host" } },
        (res) => {
          res.resume();
          res.on("end", () => resolve(res.statusCode ?? 0));
        }
      );
      req.on("error", reject);
      req.end();
    });

    expect(status).toBe(500);

    // The process survived: the server still answers normal requests.
    const after = await fetch(`http://localhost:${port}/health`);
    expect(after.status).toBe(200);
  });

  it("isolates concurrent SDK clients and removes closed sessions", async () => {
    const servers: Server[] = [];
    const serverClosed: Promise<void>[] = [];
    httpServerObj = createMcpHttpServer({
      port: 0,
      bearerToken: "secret123",
      createServer: () => {
        const server = createServer();
        serverClosed.push(new Promise<void>((resolve) => { server.onclose = resolve; }));
        servers.push(server);
        return server;
      },
    });
    port = await httpServerObj.listen();
    const clients = [1, 2].map((id) => new Client({ name: `client-${id}`, version: "1.0.0" }));
    const transports = clients.map(() => new SSEClientTransport(new URL(`http://localhost:${port}/sse`), {
      eventSourceInit: {
        fetch: (url, init) => fetch(url, {
          ...init,
          headers: { ...init?.headers, Authorization: "Bearer secret123" },
        }),
      },
      requestInit: { headers: { Authorization: "Bearer secret123" } },
    }));
    try {
      await Promise.all(clients.map((client, index) => client.connect(transports[index])));
      const results = await Promise.all(clients.map((client) => client.listTools()));
      expect(results[0].tools.length).toBeGreaterThan(0);
      expect(results[1].tools).toEqual(results[0].tools);
      expect(servers).toHaveLength(2);
      expect(servers[0]).not.toBe(servers[1]);
      const sessionId = (servers[0].transport as SSEServerTransport).sessionId;
      expect(sessionId).toBeTruthy();
      await clients[0].close();
      // Wait for the server to observe the closed SSE socket instead of polling with the 1s default.
      await Promise.race([
        serverClosed[0],
        new Promise<never>((_, reject) => {
          setTimeout(() => reject(new Error("server did not close the session within 10s of client close")), 10_000).unref();
        }),
      ]);
      expect(servers[0].transport).toBeUndefined();
      const expired = await fetch(`http://localhost:${port}/messages?sessionId=${sessionId}`, {
        method: "POST",
        headers: { Authorization: "Bearer secret123", "Content-Type": "application/json" },
        body: JSON.stringify({ jsonrpc: "2.0", method: "ping", id: 1 }),
      });
      expect(expired.status).toBe(400);
      expect((await clients[1].listTools()).tools).toEqual(results[1].tools);
    } finally {
      await Promise.all(clients.map((client) => client.close()));
    }
  }, 20_000);

  it("cleans up a session when connecting its server fails", async () => {
    const failedServer = createServer();
    vi.spyOn(failedServer, "connect").mockRejectedValue(new Error("connection failed"));
    const close = vi.spyOn(failedServer, "close");
    httpServerObj = createMcpHttpServer({
      port: 0, bearerToken: "secret123", createServer: () => failedServer,
    });
    port = await httpServerObj.listen();
    const response = await fetch(`http://localhost:${port}/sse`, {
      headers: { Authorization: "Bearer secret123" },
    });
    expect(response.status).toBe(500);
    expect(close).toHaveBeenCalledOnce();
  });

  it("should allow BoomtickMCPServer to start HTTP server via run() when transport is http", async () => {
    process.env.MCP_TRANSPORT = "http";
    process.env.PORT = "0";
    process.env.BOOMTICK_MCP_BEARER_TOKEN = "test-token";

    const boomtickServer = new BoomtickMCPServer();
    await boomtickServer.run();

    // Verify instance initialized properly
    expect(boomtickServer).toBeInstanceOf(BoomtickMCPServer);
  });
});
