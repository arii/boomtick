import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import {
  RECEIPT_FILENAME,
  readToolReceipts,
  recordToolReceipt,
  resolveReceiptDir,
} from "./session_manager.js";

describe("tool receipt write→read round trip (audit H3)", () => {
  let serverDir: string;
  let laneDir: string;

  beforeEach(() => {
    // The MCP server process cwd (where td.* tools used to record receipts when
    // repoRoot was omitted) is a different directory from the agent's worktree
    // (where agent.submit_pr reads receipts).
    serverDir = fs.mkdtempSync(path.join(os.tmpdir(), "receipt-server-"));
    laneDir = fs.mkdtempSync(path.join(os.tmpdir(), "receipt-lane-"));
    vi.spyOn(process, "cwd").mockReturnValue(serverDir);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    fs.rmSync(serverDir, { recursive: true, force: true });
    fs.rmSync(laneDir, { recursive: true, force: true });
  });

  it("a receipt written at an explicit root is read back from the same root, regardless of cwd", () => {
    // Writer side, exactly as td.init records it
    recordToolReceipt(resolveReceiptDir(laneDir), "td.init");
    // Reader side, exactly as agent.submit_pr reads it
    const read = readToolReceipts(resolveReceiptDir(laneDir));

    expect(read.error).toBeUndefined();
    expect(read.receipts.map((r) => r.tool)).toEqual(["td.init"]);
    // Nothing leaked into the server's cwd.
    expect(fs.existsSync(path.join(serverDir, RECEIPT_FILENAME))).toBe(false);
  });

  it("writer and reader fall back to the same directory when no explicit root is given", () => {
    recordToolReceipt(resolveReceiptDir(undefined), "td.rag", { query: "q" });
    const read = readToolReceipts(resolveReceiptDir(undefined));

    expect(read.error).toBeUndefined();
    expect(read.receipts).toHaveLength(1);
    expect(read.receipts[0]["tool"]).toBe("td.rag");
    // The fallback is the (mocked) process cwd, not some other ambient root.
    expect(fs.existsSync(path.join(serverDir, RECEIPT_FILENAME))).toBe(true);
  });

  it("resolves relative roots against cwd the same way on both sides", () => {
    const relative = path.relative(serverDir, laneDir);
    recordToolReceipt(resolveReceiptDir(relative), "td.verify_scope");
    const read = readToolReceipts(resolveReceiptDir(relative));

    expect(read.error).toBeUndefined();
    expect(read.receipts.map((r) => r.tool)).toEqual(["td.verify_scope"]);
  });

  it("survives rapid successive writes without losing entries or leaving temp files", () => {
    for (let seq = 0; seq < 25; seq += 1) {
      recordToolReceipt(laneDir, "td.init", { seq });
    }
    const read = readToolReceipts(laneDir);

    expect(read.receipts).toHaveLength(25);
    expect(read.receipts.map((r) => r.seq)).toEqual([...Array(25).keys()]);
    const leftovers = fs
      .readdirSync(laneDir)
      .filter((name) => name.includes(".tmp"));
    expect(leftovers).toEqual([]);
  });
});

describe("receipt parse failures are surfaced, not swallowed", () => {
  let dir: string;

  beforeEach(() => {
    dir = fs.mkdtempSync(path.join(os.tmpdir(), "receipt-corrupt-"));
  });

  afterEach(() => {
    vi.restoreAllMocks();
    fs.rmSync(dir, { recursive: true, force: true });
  });

  it("readToolReceipts reports a corrupt file instead of returning []", () => {
    fs.writeFileSync(path.join(dir, RECEIPT_FILENAME), "{not json", "utf8");
    const read = readToolReceipts(dir);

    expect(read.receipts).toEqual([]);
    expect(read.error).toContain(RECEIPT_FILENAME);
    expect(read.error).toContain("failed to parse");
  });

  it("readToolReceipts reports a non-array payload instead of returning []", () => {
    fs.writeFileSync(path.join(dir, RECEIPT_FILENAME), JSON.stringify({ tool: "td.init" }), "utf8");
    const read = readToolReceipts(dir);

    expect(read.receipts).toEqual([]);
    expect(read.error).toContain("is not a JSON array");
  });

  it("a missing receipt file is not an error", () => {
    const read = readToolReceipts(dir);

    expect(read.receipts).toEqual([]);
    expect(read.error).toBeUndefined();
  });

  it("recordToolReceipt warns and recovers when the existing file is corrupt", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    fs.writeFileSync(path.join(dir, RECEIPT_FILENAME), "garbage{", "utf8");

    recordToolReceipt(dir, "td.init");

    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("unreadable"));
    const read = readToolReceipts(dir);
    expect(read.error).toBeUndefined();
    expect(read.receipts.map((r) => r.tool)).toEqual(["td.init"]);
  });
});
