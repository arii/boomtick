/**
 * Normalizes input arguments for MCP tools:
 * 1. Converts snake_case keys to camelCase (e.g., pr_number -> prNumber).
 * 2. Maps parameter aliases (e.g., branch <-> branchName, pr_number/issue_number).
 * 3. Coerces numeric string values for expected integer fields to numbers.
 */
export function normalizeArguments(args: Record<string, unknown> | null | undefined): Record<string, unknown> {
  if (!args || typeof args !== "object") {
    return {};
  }

  const normalized: Record<string, unknown> = {};

  for (const [key, value] of Object.entries(args)) {
    // Convert snake_case to camelCase: e.g. pr_number -> prNumber
    const camelKey = key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());

    // Coerce numeric strings for number fields if applicable
    let finalValue = value;
    if (
      typeof value === "string" &&
      /^\d+$/.test(value) &&
      (camelKey.endsWith("Number") || camelKey.endsWith("Num") || camelKey === "pr" || camelKey === "limit" || camelKey.endsWith("Seconds"))
    ) {
      finalValue = parseInt(value, 10);
    }

    normalized[camelKey] = finalValue;
  }

  // Parameter Aliases & Harmonization
  if ("branch" in normalized && !("branchName" in normalized)) {
    normalized["branchName"] = normalized["branch"];
  }
  if ("branchName" in normalized && !("branch" in normalized)) {
    normalized["branch"] = normalized["branchName"];
  }

  if ("pr" in normalized && !("prNumber" in normalized)) {
    normalized["prNumber"] = normalized["pr"];
  }
  if ("issue" in normalized && !("issueNumber" in normalized)) {
    normalized["issueNumber"] = normalized["issue"];
  }

  if ("worktree" in normalized && !("worktreePath" in normalized)) {
    normalized["worktreePath"] = normalized["worktree"];
  }

  return normalized;
}
