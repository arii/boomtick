import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("child_process", () => ({ execSync: vi.fn() }));

const savedNodeEnv = process.env.NODE_ENV;
const savedCi = process.env.CI;

// Fresh module per test: initializeConfig caches in module state, so each
// case needs an unevaluated copy of dynamic.js (mocks persist across
// resetModules, but the top-level handle must be re-acquired).
async function freshDynamic() {
  vi.resetModules();
  const mod = await import("./dynamic.js");
  const child = await import("child_process");
  return { mod, mockExec: vi.mocked(child.execSync) };
}

// Regression tests for issue #1222 item (4): dynamic config used to fail
// open with warn-and-return-{} and an `any` cache. Load failures must now
// mark the process degraded (observable via isDynamicConfigDegraded) and
// wrong-typed fields must be rejected by the schema instead of flowing
// through silently.
describe("dynamic config degraded flag (issue 1222)", () => {
  beforeEach(() => {
    process.env.NODE_ENV = "test";
    process.env.CI = "false";
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    if (savedNodeEnv === undefined) delete process.env.NODE_ENV;
    else process.env.NODE_ENV = savedNodeEnv;
    if (savedCi === undefined) delete process.env.CI;
    else process.env.CI = savedCi;
    vi.restoreAllMocks();
  });

  it("marks degraded instead of returning a silent {} when td fails", async () => {
    const { mod, mockExec } = await freshDynamic();
    mockExec.mockImplementationOnce(() => {
      throw new Error("td missing");
    });
    const config = mod.initializeConfig();
    expect(config).toEqual({});
    expect(mod.isDynamicConfigDegraded()).toBe(true);
  });

  it("marks degraded on wrong-typed fields instead of flowing them through", async () => {
    const { mod, mockExec } = await freshDynamic();
    mockExec.mockReturnValueOnce(JSON.stringify({ github_repo: 123 }));
    const config = mod.initializeConfig();
    expect(config).toEqual({});
    expect(mod.isDynamicConfigDegraded()).toBe(true);
  });

  it("loads a valid config without degrading", async () => {
    const { mod, mockExec } = await freshDynamic();
    mockExec.mockReturnValueOnce(
      JSON.stringify({ github_repo: "arii/boomtick", base_branch: "main" }),
    );
    const config = mod.initializeConfig();
    expect(config.github_repo).toBe("arii/boomtick");
    expect(config.base_branch).toBe("main");
    expect(mod.isDynamicConfigDegraded()).toBe(false);
    expect(mod.getCachedDynamicConfig()).toBe(config);
  });

  it("throws in development instead of degrading silently", async () => {
    process.env.NODE_ENV = "development";
    const { mod, mockExec } = await freshDynamic();
    mockExec.mockImplementationOnce(() => {
      throw new Error("td missing");
    });
    expect(() => mod.initializeConfig()).toThrow(/CRITICAL/);
  });
});
