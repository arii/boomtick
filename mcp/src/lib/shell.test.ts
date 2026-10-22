import { describe, it, expect, vi } from "vitest";
import path from "path";
import { ALLOWED_COMMANDS, runCommand } from "./shell.js";

describe("shell helper", () => {
  it("should have a valid repo path", () => {
    const repoPath = process.env.BOOMTICK_REPO_PATH || "/app";
    expect(repoPath).toBeDefined();
    expect(path.isAbsolute(repoPath)).toBe(true);
  });

  it("should allow both td and td-cli in ALLOWED_COMMANDS", () => {
    expect(ALLOWED_COMMANDS.td).toBe("td");
    expect(ALLOWED_COMMANDS["td-cli"]).toBe("td-cli");
  });

  it("should reject disallowed commands", async () => {
    await expect(runCommand("unknown_cmd", [])).rejects.toThrow("Command not allowed: unknown_cmd");
  });
});
