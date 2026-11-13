import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("child_process", async (importOriginal) => {
  const actual = await importOriginal<typeof import("child_process")>();
  return { ...actual, spawnSync: vi.fn() };
});

// eslint-disable-next-line import/first
import { spawnSync } from "child_process";
import fs from "fs";
import os from "os";
import path from "path";
import { execSync } from "child_process";
import { getRagHealth } from "./ragHealth.js";
import { getServerHealth } from "../tools/repo.context.js";

type SpawnSyncResult = ReturnType<typeof spawnSync>;

function spawnResult(overrides: Partial<SpawnSyncResult>): SpawnSyncResult {
  return {
    pid: -1,
    output: [null, "", ""],
    signal: null,
    status: null,
    stdout: "",
    stderr: "",
    error: undefined,
    ...overrides,
  };
}

function makeTmpRepo(): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "rag-health-"));
  execSync(
    'git init -q -b main && git config user.email "t@example.com" && git config user.name "t" && git commit -q --allow-empty -m init',
    { cwd: dir, stdio: "pipe" },
  );
  return dir;
}

function writeIndex(dir: string, lastIndexedSha: string, storeBytes = 1024): void {
  const ragDir = path.join(dir, ".td_rag");
  fs.mkdirSync(path.join(ragDir, "chroma_db"), { recursive: true });
  fs.writeFileSync(path.join(ragDir, "meta.json"), JSON.stringify({ last_indexed_sha: lastIndexedSha }));
  const store = path.join(ragDir, "chroma_db", "chroma.sqlite3");
  fs.writeFileSync(store, Buffer.alloc(storeBytes, 1));
}

function headSha(dir: string): string {
  return execSync("git rev-parse HEAD", { cwd: dir, encoding: "utf-8" }).trim();
}

describe("getRagHealth", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(spawnSync).mockReturnValue(spawnResult({ status: 0, stdout: "42\n" }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("reports a never-built index when .td_rag/meta.json is missing", () => {
    const dir = makeTmpRepo();
    const health = getRagHealth(dir);
    expect(health.indexAvailable).toBe(false);
    expect(health.lastIndexedAt).toBeNull();
    expect(health.docCount).toBeNull();
    expect(health.reason).toContain("never built");
    expect(spawnSync).not.toHaveBeenCalled();
  });

  it("reports a never-built index when meta has no last_indexed_sha", () => {
    const dir = makeTmpRepo();
    fs.mkdirSync(path.join(dir, ".td_rag"), { recursive: true });
    fs.writeFileSync(path.join(dir, ".td_rag", "meta.json"), "{}");

    const health = getRagHealth(dir);
    expect(health.indexAvailable).toBe(false);
    expect(health.reason).toContain("never built");
  });

  it("reports a silent 0-hit index when the vector store file is missing or empty", () => {
    const dir = makeTmpRepo();
    const sha = headSha(dir);
    // meta written, store file absent
    fs.mkdirSync(path.join(dir, ".td_rag"), { recursive: true });
    fs.writeFileSync(path.join(dir, ".td_rag", "meta.json"), JSON.stringify({ last_indexed_sha: sha }));

    const missingStore = getRagHealth(dir);
    expect(missingStore.indexAvailable).toBe(false);
    expect(missingStore.reason).toContain("0-hit");

    // store file present but empty
    writeIndex(dir, sha, 0);
    const emptyStore = getRagHealth(dir);
    expect(emptyStore.indexAvailable).toBe(false);
    expect(emptyStore.reason).toContain("0-hit");
  });

  it("reports a silent 0-hit index when the store holds zero vectors", () => {
    const dir = makeTmpRepo();
    writeIndex(dir, headSha(dir));
    vi.mocked(spawnSync).mockReturnValue(spawnResult({ status: 0, stdout: "0\n" }));

    const health = getRagHealth(dir);
    expect(health.indexAvailable).toBe(false);
    expect(health.docCount).toBe(0);
    expect(health.reason).toContain("0 vectors");
  });

  it("reports an available index with docCount and indexCurrent when meta sha matches HEAD", () => {
    const dir = makeTmpRepo();
    writeIndex(dir, headSha(dir));

    const health = getRagHealth(dir);
    expect(health.indexAvailable).toBe(true);
    expect(health.docCount).toBe(42);
    expect(health.indexCurrent).toBe(true);
    expect(health.lastIndexedAt).not.toBeNull();
    expect(health.reason).toBeUndefined();
  });

  it("reports indexCurrent false when commits landed after the last index", () => {
    const dir = makeTmpRepo();
    writeIndex(dir, "0".repeat(40));

    const health = getRagHealth(dir);
    expect(health.indexAvailable).toBe(true);
    expect(health.indexCurrent).toBe(false);
  });

  it("returns docCount null when the count probe fails (missing python or schema drift)", () => {
    const dir = makeTmpRepo();
    writeIndex(dir, headSha(dir));
    vi.mocked(spawnSync).mockReturnValue(spawnResult({ error: new Error("spawnSync python3 ENOENT") }));

    const health = getRagHealth(dir);
    expect(health.indexAvailable).toBe(true);
    expect(health.docCount).toBeNull();
  });

  it("probes the count with shell disabled and a timeout", () => {
    const dir = makeTmpRepo();
    writeIndex(dir, headSha(dir));

    getRagHealth(dir);
    expect(spawnSync).toHaveBeenCalledWith(
      "python3",
      expect.arrayContaining(["-c"]),
      expect.objectContaining({ shell: false, timeout: expect.any(Number) }),
    );
  });
});

describe("rag health surfaced through repo_context server health", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(spawnSync).mockReturnValue(spawnResult({ status: 0, stdout: "42\n" }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("exposes a rag object alongside tdAvailable", () => {
    const health = getServerHealth();
    expect(health.tdAvailable).toBeNull();
    expect(health.rag).toBeDefined();
    expect(typeof health.rag?.indexAvailable).toBe("boolean");
    expect("docCount" in (health.rag ?? {})).toBe(true);
    expect("lastIndexedAt" in (health.rag ?? {})).toBe(true);
  });
});
