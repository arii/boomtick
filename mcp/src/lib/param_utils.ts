export function normalizeArguments(args: Record<string, unknown> | null | undefined): Record<string, unknown> {
  if (!args || typeof args !== "object") {
    return {};
  }

  const result: Record<string, unknown> = {};

  for (const [key, value] of Object.entries(args)) {
    // Convert snake_case to camelCase
    const camelKey = key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());

    // Normalize value recursively if it's an object/array
    let normalizedValue = value;
    if (Array.isArray(value)) {
      normalizedValue = value.map((item) =>
        item && typeof item === "object" ? normalizeArguments(item as Record<string, unknown>) : item
      );
    } else if (value && typeof value === "object" && !(value instanceof RegExp)) {
      normalizedValue = normalizeArguments(value as Record<string, unknown>);
    }

    // Coerce numeric string to integer for prNumber / issueNumber if applicable
    if ((camelKey === "prNumber" || camelKey === "issueNumber") && typeof normalizedValue === "string") {
      const parsedNum = parseInt(normalizedValue, 10);
      if (!isNaN(parsedNum)) {
        normalizedValue = parsedNum;
      }
    }

    result[camelKey] = normalizedValue;
  }

  // Parameter aliases harmonization
  // branch vs branchName harmonization
  if (result.branch !== undefined && result.branchName === undefined) {
    result.branchName = result.branch;
  } else if (result.branchName !== undefined && result.branch === undefined) {
    result.branch = result.branchName;
  }

  return result;
}
