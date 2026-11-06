import { describe, it, expect, vi, beforeEach } from "vitest";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { tdInitHandler } from "./td.init.js";
import { tdRagHandler } from "./td.rag.js";
import * as shellModule from "../lib/shell.js";

describe("td_init / td_rag split (#1139 item 2)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("td_init runs init and records a td.init receipt", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "td-init-"));
    const runSpy = vi.spyOn(shellModule, "runCommand").mockResolvedValueOnce({
      exitCode: 0,
      stdout: JSON.stringify({ status: "ready", head_sha: "abc" }),
      stderr: "",
    } as any);

    const res = (await tdInitHandler({ repoRoot: dir })) as any;
    expect(runSpy).toHaveBeenCalledWith("td", ["init", "--repo-root", dir, "--json"]);
    expect(res.status).toBe("ready");
    const receipts = JSON.parse(
      fs.readFileSync(path.join(dir, ".agent_tool_receipt.json"), "utf8"),
    );
    expect(receipts.map((r: any) => r.tool)).toContain("td.init");
  });

  it("td_rag queries without re-running init", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "td-rag-"));
    const runSpy = vi.spyOn(shellModule, "runCommand").mockResolvedValueOnce({
      exitCode: 0,
      stdout: JSON.stringify({ status: "success", hits: [] }),
      stderr: "",
    } as any);

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
    const receipts = JSON.parse(
      fs.readFileSync(path.join(dir, ".agent_tool_receipt.json"), "utf8"),
    );
    expect(receipts.map((r: any) => r.tool)).toContain("td.rag");
  });
});
