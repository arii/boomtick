import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import {
  MAX_TOOL_RECEIPTS,
  RECEIPT_FILENAME,
  recordToolReceipt,
} from "./session_manager.js";

function readReceipts(dir: string): Array<Record<string, unknown>> {
  const parsed: unknown = JSON.parse(
    fs.readFileSync(path.join(dir, RECEIPT_FILENAME), "utf8"),
  );
  expect(Array.isArray(parsed)).toBe(true);
  return parsed as Array<Record<string, unknown>>;
}

describe("tool receipt cap (issue #1228)", () => {
  let dir: string;
  let warnSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    dir = fs.mkdtempSync(path.join(os.tmpdir(), "receipt-cap-"));
    warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined);
  });

  afterEach(() => {
    fs.rmSync(dir, { recursive: true, force: true });
    warnSpy.mockRestore();
    vi.unstubAllEnvs();
  });

  it("pins the default cap at 500", () => {
    expect(MAX_TOOL_RECEIPTS).toBe(500);
  });

  it("trims to the newest N entries at the default cap", () => {
    const total = MAX_TOOL_RECEIPTS + 5;
    for (let seq = 0; seq < total; seq += 1) {
      recordToolReceipt(dir, "tool", { seq });
    }
    const rows = readReceipts(dir);
    expect(rows).toHaveLength(MAX_TOOL_RECEIPTS);
    expect(rows[0]["seq"]).toBe(5);
    expect(rows[rows.length - 1]["seq"]).toBe(total - 1);
  });

  it("honors a BOOMTICK_RECEIPT_CAP override and keeps the newest entries in order", () => {
    vi.stubEnv("BOOMTICK_RECEIPT_CAP", "5");
    for (let seq = 0; seq < 8; seq += 1) {
      recordToolReceipt(dir, "tool", { seq });
    }
    const rows = readReceipts(dir);
    expect(rows).toHaveLength(5);
    expect(rows.map((row) => row["seq"])).toEqual([3, 4, 5, 6, 7]);
  });

  it("falls back to the default cap with a warning on invalid override values", () => {
    for (const bad of ["banana", "0", "-3", "4.5"]) {
      const caseDir = fs.mkdtempSync(path.join(os.tmpdir(), "receipt-cap-bad-"));
      try {
        vi.stubEnv("BOOMTICK_RECEIPT_CAP", bad);
        warnSpy.mockClear();
        for (let seq = 0; seq < 3; seq += 1) {
          recordToolReceipt(caseDir, "tool", { seq });
        }
        expect(readReceipts(caseDir)).toHaveLength(3);
        expect(warnSpy).toHaveBeenCalledWith(
          expect.stringContaining("BOOMTICK_RECEIPT_CAP"),
        );
      } finally {
        fs.rmSync(caseDir, { recursive: true, force: true });
      }
    }
  });

  it("treats an empty override as unset", () => {
    vi.stubEnv("BOOMTICK_RECEIPT_CAP", "");
    recordToolReceipt(dir, "tool", { seq: 0 });
    expect(readReceipts(dir)).toHaveLength(1);
    expect(warnSpy).not.toHaveBeenCalled();
  });
});
