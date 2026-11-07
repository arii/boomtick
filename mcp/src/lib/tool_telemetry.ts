import * as fs from "node:fs";
import * as path from "node:path";

export const TELEMETRY_FILENAME = ".agent_tool_telemetry.jsonl";

export interface ToolTelemetryLine {
  tool: string;
  /** Lane session locus: MCP tool handlers carry no session id, so the
   * worktree path they ran against identifies the calling session. */
  session: string;
  ok: boolean;
  ms: number;
  ts: string;
  detail?: string;
}

/**
 * Append one JSON telemetry line per tool call (issue #1157).
 *
 * Best-effort: telemetry must never break the tool it observes, so
 * write failures are swallowed. The lane audits compliance by reading
 * these lines next to the scope-gate receipts.
 */
export function emitToolTelemetry(
  worktreePath: string,
  tool: string,
  ok: boolean,
  ms: number,
  detail?: string,
): void {
  try {
    const line: ToolTelemetryLine = {
      tool,
      session: worktreePath,
      ok,
      ms: Math.max(0, Math.round(ms)),
      ts: new Date().toISOString(),
    };
    if (detail !== undefined) {
      line.detail = detail;
    }
    fs.appendFileSync(
      path.join(worktreePath, TELEMETRY_FILENAME),
      JSON.stringify(line) + "\n",
      "utf8",
    );
  } catch {
    // Telemetry is observability, not control flow.
  }
}
