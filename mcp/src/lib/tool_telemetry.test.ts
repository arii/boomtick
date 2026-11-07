import { describe, it, expect } from "vitest";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import {
  emitToolTelemetry,
  TELEMETRY_FILENAME,
  type ToolTelemetryLine,
} from "./tool_telemetry.js";

function readLines(dir: string): ToolTelemetryLine[] {
  return fs
    .readFileSync(path.join(dir, TELEMETRY_FILENAME), "utf8")
    .split("\n")
    .filter((l) => l.trim().length > 0)
    .map((l) => JSON.parse(l) as ToolTelemetryLine);
}

describe("tool telemetry (issue #1157)", () => {
  it("emits one JSON line per call with tool/session/ok/ms", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "telemetry-"));
    emitToolTelemetry(dir, "agent.submit_pr", true, 12.6, "ok");
    emitToolTelemetry(dir, "td.init_and_rag", false, 3, "denied");

    const [first, second] = readLines(dir);
    expect(first.tool).toBe("agent.submit_pr");
    expect(first.session).toBe(dir);
    expect(first.ok).toBe(true);
    expect(first.ms).toBe(13);
    expect(typeof first.ts).toBe("string");
    expect(first.detail).toBe("ok");
    expect(second.tool).toBe("td.init_and_rag");
    expect(second.ok).toBe(false);
    expect(second.detail).toBe("denied");
  });

  it("omits detail when not given and clamps ms", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "telemetry-"));
    emitToolTelemetry(dir, "t", true, -5);
    const [line] = readLines(dir);
    expect(line.ms).toBe(0);
    expect("detail" in line).toBe(false);
  });

  it("never throws when the directory is missing", () => {
    const missing = path.join(os.tmpdir(), "telemetry-no-such-dir-xyz");
    expect(() =>
      emitToolTelemetry(missing, "t", true, 1),
    ).not.toThrow();
    expect(fs.existsSync(path.join(missing, TELEMETRY_FILENAME))).toBe(false);
  });
});
