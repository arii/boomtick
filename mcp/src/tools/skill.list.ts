import { SkillListInput, SkillListInputSchema } from "./contract.js";
import { resolveRepoPath } from "../lib/git.js";
import { listSkills } from "../lib/skills.js";

export { SkillListInputSchema };

export async function skillListHandler(args: SkillListInput) {
  const parsed = SkillListInputSchema.parse(args);
  const baseRepoPath = resolveRepoPath({ repo: parsed.repo ?? null, path: parsed.path ?? null });
  const skills = await listSkills(baseRepoPath);

  return { skills };
}
