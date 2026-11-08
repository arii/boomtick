import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("child_process", () => ({
  execSync: vi.fn(),
}));

import { execSync } from "child_process";
import { resolveRepo } from "./git.js";

const mockedExecSync = vi.mocked(execSync);

describe("resolveRepo failure behavior", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("returns the trimmed explicit repo without touching git", () => {
    expect(resolveRepo("  owner/name  ", "/tmp/never-used-cwd-a")).toBe("owner/name");
    expect(mockedExecSync).not.toHaveBeenCalled();
  });

  it("parses owner/repo from an SSH remote url and caches it per cwd", () => {
    const cwd = "/tmp/resolve-repo-ssh-cache";
    mockedExecSync.mockReturnValue("git@github.com:acme/widgets.git\n" as never);

    expect(resolveRepo(null, cwd)).toBe("acme/widgets");

    // Second call for the same cwd must be served from cache: no new git call.
    expect(resolveRepo(undefined, cwd)).toBe("acme/widgets");
    expect(mockedExecSync).toHaveBeenCalledTimes(1);
    expect(mockedExecSync).toHaveBeenCalledWith(
      "git remote get-url origin",
      expect.objectContaining({ cwd })
    );
  });

  it("parses owner/repo from an HTTPS remote url", () => {
    const cwd = "/tmp/resolve-repo-https-cache";
    mockedExecSync.mockReturnValue("https://github.com/acme/gadgets.git\n" as never);

    expect(resolveRepo(null, cwd)).toBe("acme/gadgets");
    expect(mockedExecSync).toHaveBeenCalledTimes(1);
  });

  it("throws naming the cwd and the git cause when git fails", () => {
    const cwd = "/tmp/resolve-repo-git-failure";
    const cause = "Command failed: git remote get-url origin";
    mockedExecSync.mockImplementation(() => {
      throw new Error(cause);
    });

    let thrown: unknown;
    try {
      resolveRepo(null, cwd);
    } catch (e) {
      thrown = e;
    }
    expect(thrown).toBeInstanceOf(Error);
    const message = (thrown as Error).message;
    // The error must identify WHERE detection was attempted and WHY it failed.
    expect(message).toContain(cwd);
    expect(message).toContain(cause);
  });

  it("throws naming the cwd when the remote url is unparseable", () => {
    const cwd = "/tmp/resolve-repo-unparseable-url";
    mockedExecSync.mockReturnValue("not-a-remote-url\n" as never);

    let thrown: unknown;
    try {
      resolveRepo(null, cwd);
    } catch (e) {
      thrown = e;
    }
    expect(thrown).toBeInstanceOf(Error);
    const message = (thrown as Error).message;
    expect(message).toContain(cwd);
    expect(message).toContain("could not parse");
  });

  it("does not cache git failures: a failed cwd is retried and can succeed", () => {
    const cwd = "/tmp/resolve-repo-failure-retry";
    mockedExecSync.mockImplementation(() => {
      throw new Error("fatal: not a git repository");
    });
    expect(() => resolveRepo(null, cwd)).toThrow();

    // The failure must not be stuck in the cache: a later attempt re-runs git
    // and a healthy remote now resolves.
    mockedExecSync.mockReturnValue("git@github.com:acme/recovered.git\n" as never);
    expect(resolveRepo(null, cwd)).toBe("acme/recovered");
    expect(mockedExecSync).toHaveBeenCalledTimes(2);

    // And the recovered value is now the cached one.
    expect(resolveRepo(null, cwd)).toBe("acme/recovered");
    expect(mockedExecSync).toHaveBeenCalledTimes(2);
  });

  it("does not cache unparseable urls: a bad remote is re-read on retry", () => {
    const cwd = "/tmp/resolve-repo-unparseable-retry";
    mockedExecSync.mockReturnValue("garbage-remote\n" as never);
    expect(() => resolveRepo(null, cwd)).toThrow();

    mockedExecSync.mockReturnValue("git@github.com:acme/fixed.git\n" as never);
    expect(resolveRepo(null, cwd)).toBe("acme/fixed");
    expect(mockedExecSync).toHaveBeenCalledTimes(2);
  });
});
