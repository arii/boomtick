import { spawnSync } from "child_process";

export interface TdPreflightResult {
  available: boolean;
  /** Why the check failed; only set when available is false. */
  reason?: string;
}

// Runs `td doctor` once at startup. Deliberately non-fatal: a missing or
// broken td only degrades the td.* tools, and the server must stay up to
// report the problem through boomtick_health.
export function checkTdAvailability(cwd: string): TdPreflightResult {
  const result = spawnSync("td", ["doctor"], {
    encoding: "utf-8",
    cwd,
    shell: false, // Explicitly disabled to clear Semgrep rules
  });

  if (result.error) {
    return { available: false, reason: `td is not resolvable on PATH: ${result.error.message}` };
  }

  if (result.status !== 0) {
    return { available: false, reason: `td doctor returned exit code: ${result.status}` };
  }

  return { available: true };
}

// Startup preflight outcome, surfaced through boomtick_health. null until
// the preflight has run.
let preflight: TdPreflightResult | null = null;

export function recordTdPreflight(result: TdPreflightResult): void {
  preflight = result;
}

export function getTdPreflight(): TdPreflightResult | null {
  return preflight;
}

export function resetTdPreflightForTests(): void {
  preflight = null;
}
