import { describe, it, expect, beforeEach, afterEach } from "vitest";
import fs from "fs/promises";
import os from "os";
import path from "path";
import { listSkills, readSkill } from "../lib/skills.js";

describe("session skills", () => {
  let tmpRepoDir: string;

  beforeEach(async () => {
    tmpRepoDir = await fs.mkdtemp(path.join(os.tmpdir(), "bt-skills-"));
    await fs.mkdir(path.join(tmpRepoDir, ".agents", "skills", "alpha"), { recursive: true });
    await fs.writeFile(
      path.join(tmpRepoDir, ".agents", "skills", "alpha", "SKILL.md"),
      '---\nname: alpha\ndescription: "First playbook."\n---\n\n# Alpha\n'
    );
    await fs.mkdir(path.join(tmpRepoDir, ".agents", "skills", "beta"), { recursive: true });
    await fs.writeFile(
      path.join(tmpRepoDir, ".agents", "skills", "beta", "SKILL.md"),
      "# Beta has no frontmatter\n"
    );
  });

  afterEach(async () => {
    try {
      await fs.rm(tmpRepoDir, { recursive: true, force: true });
    } catch {
      // ignore
    }
  });

  it("lists skills with descriptions, sorted", async () => {
    const skills = await listSkills(tmpRepoDir);
    expect(skills).toEqual([
      { name: "alpha", description: "First playbook." },
      { name: "beta", description: "" },
    ]);
  });

  it("returns empty list without a skills dir", async () => {
    const empty = await fs.mkdtemp(path.join(os.tmpdir(), "bt-noskills-"));
    try {
      expect(await listSkills(empty)).toEqual([]);
    } finally {
      await fs.rm(empty, { recursive: true, force: true });
    }
  });

  it("reads a skill body and rejects traversal", async () => {
    const body = await readSkill(tmpRepoDir, "alpha");
    expect(body).toContain("# Alpha");
    await expect(readSkill(tmpRepoDir, "../escape")).rejects.toThrow(/Invalid skill name/);
    await expect(readSkill(tmpRepoDir, "missing")).rejects.toThrow(/not found/);
  });
});
