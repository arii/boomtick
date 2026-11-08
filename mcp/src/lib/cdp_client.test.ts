import { describe, it, expect, vi, beforeEach } from "vitest";
import * as shell from "./shell.js";
import { getVisualDiff } from "./cdp_client.js";

vi.mock("./shell.js", () => ({
  runCommand: vi.fn(),
}));

function mockTd(payload: unknown, argv: string[] = []) {
  vi.mocked(shell.runCommand).mockResolvedValue({
    stdout: JSON.stringify(payload),
    stderr: "",
    exitCode: 0,
    durationMs: 5,
    command: ["td", ...argv].join(" "),
  });
}

describe("cdp_client", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns the visual_diff payload on a reachable snapshot", async () => {
    mockTd({
      passed: true,
      ui_changed: true,
      visual_diff: {
        reachable: true,
        url: "http://preview:3000/",
        mismatch_percentage: 0.0,
        dom_node_count: 42,
        interactive_elements: 7,
        screenshot_path: "/tmp/snap.png",
        error: null,
      },
    });
    const result = await getVisualDiff("/wt", "http://preview:3000/");
    expect(result.passed).toBe(true);
    expect(result.ui_changed).toBe(true);
    expect(result.visual_diff?.dom_node_count).toBe(42);
    expect(result.error).toBeUndefined();
    const argv = vi.mocked(shell.runCommand).mock.calls[0][1];
    expect(argv).toContain("--preview-url");
    expect(argv).toContain("http://preview:3000/");
  });

  it("surfaces BROWSER_UNREACHABLE as a failed gate", async () => {
    mockTd({
      passed: false,
      ui_changed: true,
      visual_diff: {
        reachable: false,
        url: "http://preview:3000/",
        mismatch_percentage: 0.0,
        dom_node_count: 0,
        interactive_elements: 0,
        screenshot_path: null,
        error: "BROWSER_UNREACHABLE: refused",
      },
      error: "BROWSER_UNREACHABLE: refused",
    });
    const result = await getVisualDiff("/wt", "http://preview:3000/");
    expect(result.passed).toBe(false);
    expect(result.visual_diff?.reachable).toBe(false);
    expect(result.error).toContain("BROWSER_UNREACHABLE");
  });

  it("omits --preview-url when no preview is given", async () => {
    mockTd({ passed: true, ui_changed: false, visual_diff: null });
    const result = await getVisualDiff("/wt");
    expect(result.visual_diff).toBeNull();
    const argv = vi.mocked(shell.runCommand).mock.calls[0][1];
    expect(argv).not.toContain("--preview-url");
  });
});
