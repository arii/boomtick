import path from "path";
import * as syncFs from "fs";
import fs from "fs/promises";

export interface SkillSummary {
  name: string;
  description: string;
}

function skillsDir(baseRepoPath: string): string {
  return path.join(baseRepoPath, ".agents", "skills");
}

function parseDescription(body: string): string {
  const match = body.match(/^description:\s*["']?(.+?)["']?\s*$/m);
  return match ? match[1].trim() : "";
}

export async function listSkills(baseRepoPath: string): Promise<SkillSummary[]> {
  const dir = skillsDir(baseRepoPath);
  let entries;
  try {
    entries = await fs.readdir(dir, { withFileTypes: true });
  } catch {
    return [];
  }
  const out: SkillSummary[] = [];
  for (const entry of entries) {
    if (!entry.isDirectory()) {
      continue;
    }
    const skillFile = path.join(dir, entry.name, "SKILL.md");
    try {
      const body = await fs.readFile(skillFile, "utf-8");
      out.push({ name: entry.name, description: parseDescription(body) });
    } catch {
      // Missing/unreadable SKILL.md: list the name without description.
      out.push({ name: entry.name, description: "" });
    }
  }
  out.sort((a, b) => a.name.localeCompare(b.name));
  return out;
}

export async function readSkill(baseRepoPath: string, name: string): Promise<string> {
  if (!/^[A-Za-z0-9_-]+$/.test(name)) {
    throw new Error(`Invalid skill name: ${name}`);
  }
  const skillFile = path.join(skillsDir(baseRepoPath), name, "SKILL.md");
  const resolved = path.resolve(skillFile);
  if (!resolved.startsWith(path.resolve(skillsDir(baseRepoPath)) + path.sep)) {
    throw new Error(`Invalid skill name: ${name}`);
  }
  if (!syncFs.existsSync(resolved)) {
    throw new Error(`Skill not found: ${name}`);
  }
  return fs.readFile(resolved, "utf-8");
}
