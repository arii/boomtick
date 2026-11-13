// Pure transport/port/token selection for the MCP server.
//
// Audit H5: HTTP must never be selected implicitly. A service manager
// exporting PORT (systemd, fly.io, heroku, ...) used to silently flip a
// stdio server to HTTP, leaving stdio clients hanging on a closed stdin.
// HTTP now requires an explicit opt-in: the --http flag or
// MCP_TRANSPORT=http. PORT / HTTP_PORT only choose the port to listen on
// when HTTP was explicitly requested.

export type McpTransport = "stdio" | "http";

export interface TransportSelection {
  transport: McpTransport;
  port: number;
  bearerToken: string | undefined;
}

const DEFAULT_PORT = 3000;

function parsePort(value: string | undefined): number | undefined {
  if (value === undefined) return undefined;
  const port = Number.parseInt(value, 10);
  return Number.isFinite(port) && port >= 0 ? port : undefined;
}

export function resolveTransport(
  args: readonly string[],
  env: NodeJS.ProcessEnv = process.env,
): TransportSelection {
  const hasFlag = (flag: string) => args.includes(flag) || args.some((a) => a.startsWith(`${flag}=`));

  // Explicit flags beat env; anything implicit stays stdio.
  const httpRequested = hasFlag("--http") || env.MCP_TRANSPORT === "http";
  const transport: McpTransport = !hasFlag("--stdio") && httpRequested ? "http" : "stdio";

  const flagPort = (() => {
    for (let i = 0; i < args.length; i++) {
      if (args[i] === "--port" && i + 1 < args.length) return parsePort(args[i + 1]);
      if (args[i]?.startsWith("--port=")) return parsePort(args[i]?.split("=")[1]);
    }
    return undefined;
  })();

  const bearerFlag = (() => {
    for (let i = 0; i < args.length; i++) {
      if (args[i] === "--bearer-token" && i + 1 < args.length) return args[i + 1];
      if (args[i]?.startsWith("--bearer-token=")) return args[i]?.split("=").slice(1).join("=");
    }
    return undefined;
  })();

  const port =
    flagPort ??
    (transport === "http" ? parsePort(env.PORT) ?? parsePort(env.HTTP_PORT) ?? DEFAULT_PORT : DEFAULT_PORT);

  const bearerToken =
    bearerFlag ?? env.BOOMTICK_MCP_BEARER_TOKEN ?? env.MCP_BEARER_TOKEN ?? env.AUTH_TOKEN;

  return { transport, port, bearerToken: bearerToken || undefined };
}
