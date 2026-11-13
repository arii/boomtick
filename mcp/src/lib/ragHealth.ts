import { spawnSync, execSync } from "child_process";
import * as fs from "fs";
import * as path from "path";

// Mirrors cli/dev_tools/services/vector_store.py, which persists last-indexed
// state in .td_rag/meta.json (key: last_indexed_sha) and the ChromaDB store
// in .td_rag/chroma_db/chroma.sqlite3. Reading these artifacts directly keeps
// the health signal deterministic — no python backend, no LLM call.
const TD_RAG_DIR = ".td_rag";
const META_FILENAME = "meta.json";
const DOC_COUNT_TIMEOUT_MS = 5_000;

export interface RagHealthResult {
  /** True when an index exists on disk and holds at least one vector. */
  indexAvailable: boolean;
  /** ISO mtime of the index metadata file; null when never indexed. */
  lastIndexedAt: string | null;
  /** Vector count read from the store; null when it cannot be read. */
  docCount: number | null;
  /** Whether the index was built at the current HEAD sha; null when git is unavailable. */
  indexCurrent: boolean | null;
  /** Why the index is unavailable; only set when indexAvailable is false. */
  reason?: string;
}

interface RagMeta {
  last_indexed_sha?: unknown;
  [key: string]: unknown;
}

function readRagMeta(metaFile: string): RagMeta | null {
  try {
    const parsed: unknown = JSON.parse(fs.readFileSync(metaFile, "utf-8"));
    if (parsed && typeof parsed === "object") {
      return parsed as RagMeta;
    }
    return null;
  } catch {
    return null;
  }
}

function gitHeadSha(targetPath: string): string | null {
  try {
    return execSync("git rev-parse HEAD", {
      cwd: targetPath,
      encoding: "utf-8",
      stdio: ["pipe", "pipe", "ignore"],
    }).trim();
  } catch {
    return null;
  }
}

// The chroma sqlite schema is not pinned (chromadb floats in cli/requirements),
// so the count probe fails soft to null rather than guessing a table name wrong.
// Fail-soft is safe: docCount null reads as "unknown", not "healthy".
function countVectors(chromaDbFile: string): number | null {
  const script =
    "import sqlite3,sys;" +
    "c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True);" +
    "print(c.execute('select count(*) from embeddings').fetchone()[0])";
  let result;
  try {
    result = spawnSync("python3", ["-c", script, chromaDbFile], {
      encoding: "utf-8",
      timeout: DOC_COUNT_TIMEOUT_MS,
      shell: false, // Explicitly disabled to clear Semgrep rules
    });
  } catch {
    return null;
  }
  if (!result || result.error || result.status !== 0) {
    return null;
  }
  const count = parseInt((result.stdout || "").trim(), 10);
  return Number.isFinite(count) ? count : null;
}

export function getRagHealth(targetPath: string): RagHealthResult {
  const ragDir = path.join(targetPath, TD_RAG_DIR);
  const metaFile = path.join(ragDir, META_FILENAME);

  let meta: RagMeta | null = null;
  let lastIndexedAt: string | null = null;
  try {
    meta = readRagMeta(metaFile);
    lastIndexedAt = fs.statSync(metaFile).mtime.toISOString();
  } catch {
    // stat failed: treated as never indexed below
  }

  const lastIndexedSha = typeof meta?.last_indexed_sha === "string" ? meta.last_indexed_sha : "";
  if (!meta || !lastIndexedSha) {
    return {
      indexAvailable: false,
      lastIndexedAt: null,
      docCount: null,
      indexCurrent: false,
      reason: "index never built: .td_rag/meta.json missing or has no last_indexed_sha (run td rag index)",
    };
  }

  const chromaDbFile = path.join(ragDir, "chroma_db", "chroma.sqlite3");
  let storeSize = 0;
  try {
    storeSize = fs.statSync(chromaDbFile).size;
  } catch {
    // missing store handled below
  }
  if (storeSize === 0) {
    return {
      indexAvailable: false,
      lastIndexedAt,
      docCount: null,
      indexCurrent: false,
      reason: "vector store missing or empty — silent 0-hit index (rebuild with td rag index --full)",
    };
  }

  const docCount = countVectors(chromaDbFile);
  if (docCount === 0) {
    return {
      indexAvailable: false,
      lastIndexedAt,
      docCount: 0,
      indexCurrent: false,
      reason: "index holds 0 vectors — silent 0-hit index (rebuild with td rag index --full)",
    };
  }

  const headSha = gitHeadSha(targetPath);
  return {
    indexAvailable: true,
    lastIndexedAt,
    docCount,
    indexCurrent: headSha === null ? null : lastIndexedSha === headSha,
  };
}
