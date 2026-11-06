import { describe, it, expect, vi, beforeEach } from "vitest";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { tdInitHandler } from "./td.init.js";
import { tdRagHandler } from "./td.rag.js";
import * as shellModule from "../lib/shell.js";
import type { ShellResult } from "../lib/shell.js";

function shellOk(stdout: string): ShellResult {
  return { exitCode: 0, stdout, stderr: "", durationMs: 0, command: "td" };
}

function readReceiptTools(dir: string): string[] {
  const receipts: Array<{ tool: string }> = JSON.parse(
    fs.readFileSync(path.join(dir, ".agent_tool_receipt.json"), "utf8"),
  );
  return receipts.map((r) => r.tool);
}

describe("td_init / td_rag split (issue 1139, item 2)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("td_init runs init and records a td.init receipt", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "td-init-"));
    const runSpy = vi
      .spyOn(shellModule, "runCommand")
      .mockResolvedValueOnce(
        shellOk(JSON.stringify({ status: "ready", head_sha: "abc" })),
      );

    const res = await tdInitHandler({ repoRoot: dir });
    expect(runSpy).toHaveBeenCalledWith("td", ["init", "--repo-root", dir, "--json"]);
    expect(res.status).toBe("ready");
    expect(readReceiptTools(dir)).toContain("td.init");
  });

  it("td_rag queries without re-running init", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "td-rag-"));
    const runSpy = vi.spyOn(shellModule, "runCommand").mockResolvedValueOnce(
      shellOk(JSON.stringify({ status: "success", hits: [] })),
    );

    await tdRagHandler({ repoRoot: dir, query: "scope gate", topK: 3 });
    expect(runSpy).toHaveBeenCalledTimes(1);
    expect(runSpy).toHaveBeenCalledWith("td", [
      "rag",
      "query",
      "--query",
      "scope gate",
      "--repo-root",
      dir,
      "--top-k",
      "3",
      "--json",
    ]);
    expect(readReceiptTools(dir)).toContain("td.rag");
  });
});
