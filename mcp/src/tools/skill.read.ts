import { SkillReadInput, SkillReadInputSchema } from "./contract.js";
import { resolveRepoPath } from "../lib/git.js";
import { readSkill } from "../lib/skills.js";

export { SkillReadInputSchema };

export async function skillReadHandler(args: SkillReadInput) {
  const parsed = SkillReadInputSchema.parse(args);
  const baseRepoPath = resolveRepoPath({ repo: parsed.repo ?? null, path: parsed.path ?? null });
  const body = await readSkill(baseRepoPath, parsed.name);

  return {
    name: parsed.name,
    body,
  };
}
