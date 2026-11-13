import { describe, it, expect } from "vitest";
import { resolveTransport } from "./transport.js";

const env = (over: Record<string, string> = {}): NodeJS.ProcessEnv => ({ ...over }) as NodeJS.ProcessEnv;

describe("resolveTransport", () => {
  it("defaults to stdio on port 3000 with no env or flags", () => {
    expect(resolveTransport([], env())).toEqual({ transport: "stdio", port: 3000, bearerToken: undefined });
  });

  it("audit H5 regression: PORT does not implicitly flip stdio to HTTP", () => {
    const selection = resolveTransport([], env({ PORT: "8080" }));
    expect(selection.transport).toBe("stdio");
    expect(selection.port).toBe(3000);
  });

  it("audit H5 regression: HTTP_PORT does not implicitly flip stdio to HTTP", () => {
    const selection = resolveTransport([], env({ HTTP_PORT: "8080" }));
    expect(selection.transport).toBe("stdio");
    expect(selection.port).toBe(3000);
  });

  it("selects HTTP on the --http flag", () => {
    expect(resolveTransport(["--http"], env()).transport).toBe("http");
    expect(resolveTransport(["--http=1"], env()).transport).toBe("http");
  });

  it("selects HTTP on MCP_TRANSPORT=http", () => {
    expect(resolveTransport([], env({ MCP_TRANSPORT: "http" })).transport).toBe("http");
  });

  it("MCP_TRANSPORT=stdio stays stdio", () => {
    expect(resolveTransport([], env({ MCP_TRANSPORT: "stdio" })).transport).toBe("stdio");
  });

  it("an explicit --stdio flag beats MCP_TRANSPORT=http", () => {
    const selection = resolveTransport(["--stdio"], env({ MCP_TRANSPORT: "http" }));
    expect(selection.transport).toBe("stdio");
  });

  it("uses PORT as the HTTP port once HTTP is explicitly selected", () => {
    const selection = resolveTransport([], env({ MCP_TRANSPORT: "http", PORT: "9000" }));
    expect(selection).toMatchObject({ transport: "http", port: 9000 });
  });

  it("falls back to HTTP_PORT then the default when explicitly HTTP", () => {
    expect(resolveTransport([], env({ MCP_TRANSPORT: "http", HTTP_PORT: "9001" })).port).toBe(9001);
    expect(resolveTransport([], env({ MCP_TRANSPORT: "http" })).port).toBe(3000);
  });

  it("the --port flag beats env PORT in either --port N or --port=N form", () => {
    expect(resolveTransport(["--http", "--port", "7777"], env({ PORT: "9000" })).port).toBe(7777);
    expect(resolveTransport(["--http", "--port=7778"], env({ PORT: "9000" })).port).toBe(7778);
  });

  it("ignores non-numeric or negative port env values", () => {
    expect(resolveTransport([], env({ MCP_TRANSPORT: "http", PORT: "not-a-port" })).port).toBe(3000);
    expect(resolveTransport([], env({ MCP_TRANSPORT: "http", PORT: "-1" })).port).toBe(3000);
  });

  it("the --bearer-token flag beats bearer-token env vars", () => {
    const selection = resolveTransport(["--bearer-token", "flag-token"], env({ MCP_BEARER_TOKEN: "env-token" }));
    expect(selection.bearerToken).toBe("flag-token");
    expect(resolveTransport(["--bearer-token=flag-token"], env()).bearerToken).toBe("flag-token");
  });

  it("resolves bearer tokens from env in documented precedence order", () => {
    expect(resolveTransport([], env({ BOOMTICK_MCP_BEARER_TOKEN: "a", MCP_BEARER_TOKEN: "b", AUTH_TOKEN: "c" })).bearerToken).toBe("a");
    expect(resolveTransport([], env({ MCP_BEARER_TOKEN: "b", AUTH_TOKEN: "c" })).bearerToken).toBe("b");
    expect(resolveTransport([], env({ AUTH_TOKEN: "c" })).bearerToken).toBe("c");
  });
});
