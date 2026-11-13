// Process-level crash guards (audit H5): a single unhandled rejection or
// uncaught exception must not take the MCP server down mid-session — log
// to stderr and keep serving. Idempotent so repeated run() calls (tests,
// multiple entrypoints) never register duplicate listeners.

export function installProcessGuards(): void {
  const guarded = process as NodeJS.Process & { __boomtickGuardsInstalled?: boolean };
  if (guarded.__boomtickGuardsInstalled) return;
  guarded.__boomtickGuardsInstalled = true;

  process.on("unhandledRejection", (reason) => {
    console.error("Unhandled promise rejection (server kept alive):", reason);
  });

  process.on("uncaughtException", (error) => {
    console.error("Uncaught exception (server kept alive):", error);
  });
}
