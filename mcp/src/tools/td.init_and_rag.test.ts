import { describe, it, expect, vi, beforeEach } from "vitest";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { tdInitAndRagHandler } from "./td.init_and_rag.js";
import * as shellModule from "../lib/shell.js";
import type { ShellResult } from "../lib/shell.js";

function shellOk(stdout: string): ShellResult {
  return { exitCode: 0, stdout, stderr: "", durationMs: 0, command: "td" };
}

function readTelemetry(dir: string): Array<Record<string, unknown>> {
  return fs
    .readFileSync(path.join(dir, ".agent_tool_telemetry.jsonl"), "utf8")
    .split("\n")
    .filter((l) => l.trim().length > 0)
    .map((l) => JSON.parse(l) as Record<string, unknown>);
}

function readReceiptTools(dir: string): string[] {
  const receipts: Array<{ tool: string }> = JSON.parse(
    fs.readFileSync(path.join(dir, ".agent_tool_receipt.json"), "utf8"),
  );
  return receipts.map((r) => r.tool);
}

describe("td_init_and_rag telemetry (issue #1157)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("records receipt and ok telemetry without a query", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "td-init-and-rag-"));
    vi.spyOn(shellModule, "runCommand").mockResolvedValueOnce(
      shellOk(JSON.stringify({ status: "ready", head_sha: "abc" })),
    );

    const res = await tdInitAndRagHandler({ repoRoot: dir });
    expect((res as { status: string }).status).toBe("ready");
    expect(readReceiptTools(dir)).toContain("td.init_and_rag");
    const [line] = readTelemetry(dir);
    expect(line.tool).toBe("td.init_and_rag");
    expect(line.session).toBe(dir);
    expect(line.ok).toBe(true);
  });

  it("queries, then records receipt and ok telemetry", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "td-init-and-rag-"));
    const runSpy = vi
      .spyOn(shellModule, "runCommand")
      .mockResolvedValueOnce(shellOk(JSON.stringify({ status: "ready" })))
      .mockResolvedValueOnce(
        shellOk(JSON.stringify({ status: "success", hits: [] })),
      );

    const res = await tdInitAndRagHandler({ repoRoot: dir, query: "scope gate", topK: 3 });
    expect(runSpy).toHaveBeenCalledTimes(2);
    expect(res).toHaveProperty("rag");
    expect(readReceiptTools(dir)).toContain("td.init_and_rag");
    const [line] = readTelemetry(dir);
    expect(line.ok).toBe(true);
  });

  it("emits fail telemetry and rethrows when td fails", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "td-init-and-rag-"));
    vi.spyOn(shellModule, "runCommand").mockRejectedValueOnce(new Error("td down"));

    await expect(tdInitAndRagHandler({ repoRoot: dir })).rejects.toThrow("td down");
    const [line] = readTelemetry(dir);
    expect(line.tool).toBe("td.init_and_rag");
    expect(line.ok).toBe(false);
    expect(line.detail).toMatch("td down");
  });
});
