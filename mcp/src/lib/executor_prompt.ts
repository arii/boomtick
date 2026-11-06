// Executor system-prompt template (mirrors arii/remote-server
// deep-agent/EXECUTOR_PROMPT.md placeholder contract). Kept as a
// TS constant: plain tsc does not emit loose .md assets into dist.
export const EXECUTOR_PROMPT_TEMPLATE = [
  "You are an executor agent running in an isolated git worktree. You",
  "see only this worktree and the task brief below. Implement exactly",
  "what the brief names — never widen scope. Verify with the repo's",
  "own commands and report back. Your authority ends at reporting —",
  "you never merge.",
  "",
  "Repo: {{REPO}}",
  "Worktree: {{WORKTREE_PATH}} (branch {{BRANCH}}, base {{BASE_BRANCH}})",
  "Agent contract: {{AGENT_CONTRACT}}",
  "Approved proposal: {{PROPOSAL}}",
  "Task brief: {{TASK_BRIEF}}",
  "Report back to: {{DISPATCHER}}",
  "",
  "Deterministic commands first: td, gh, git, and the contract's",
  "build/test commands answer factual questions faster than any model",
  "call. The LLM (you) is for judgment, not retrieval.",
].join("\n");

export interface ExecutorPromptVars {
  repo: string;
  worktreePath: string;
  branch: string;
  baseBranch: string;
  agentContract: string;
  proposal: string;
  taskBrief: string;
  dispatcher: string;
}

// Fills every {{PLACEHOLDER}}; throws on any leftover so an
// executor never receives an unfilled template.
export function fillExecutorPrompt(
  template: string,
  vars: ExecutorPromptVars,
): string {
  const filled = template
    .replaceAll("{{REPO}}", vars.repo)
    .replaceAll("{{WORKTREE_PATH}}", vars.worktreePath)
    .replaceAll("{{BRANCH}}", vars.branch)
    .replaceAll("{{BASE_BRANCH}}", vars.baseBranch)
    .replaceAll("{{AGENT_CONTRACT}}", vars.agentContract)
    .replaceAll("{{PROPOSAL}}", vars.proposal)
    .replaceAll("{{TASK_BRIEF}}", vars.taskBrief)
    .replaceAll("{{DISPATCHER}}", vars.dispatcher);
  const leftover = filled.match(/\{\{[A-Z_]+\}\}/);
  if (leftover) {
    throw new Error(`Unfilled executor prompt placeholder: ${leftover[0]}`);
  }
  return filled;
}
