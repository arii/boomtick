import { describe, expect, it } from "vitest";
import { multiExecHandler } from "./repo.multi_exec.js";

describe("MultiExec Tool", () => {
  it("should execute a command sequentially across repositories", async () => {
    const res = await multiExecHandler({
      command: "echo test-vitest-exec",
      repos: ["arii/boomtick"],
    });

    expect(res.status).toBe("success");
    expect(res.total_repos).toBe(1);
    expect(res.results[0].stdout).toContain("test-vitest-exec");
  });
});
