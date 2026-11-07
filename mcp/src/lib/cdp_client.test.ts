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

describe("cdp cursor and input dispatch (#1144)", () => {
  function fakeSender(center: { x: number; y: number } | null = { x: 10, y: 20 }) {
    const calls: Array<{ method: string; params?: Record<string, unknown> }> = [];
    const send = async (method: string, params?: Record<string, unknown>) => {
      calls.push({ method, params });
      if (method === "Runtime.evaluate" && params && typeof params.expression === "string" && params.expression.includes("getBoundingClientRect")) {
        return { result: center ? { value: center } : {} };
      }
      return {};
    };
    return { calls, send };
  }

  it("overlays the cursor before clicking", async () => {
    const { cdpClick } = await import("./cdp_client.js");
    const { calls, send } = fakeSender();
    const pt = await cdpClick(send, { selector: "button" });
    expect(pt).toEqual({ x: 10, y: 20 });
    const methods = calls.map((c) => c.method);
    expect(methods).toContain("Page.addScriptToEvaluateOnNewDocument");
    expect(methods).toContain("Input.dispatchMouseEvent");
    const pressed = calls.find((c) => c.method === "Input.dispatchMouseEvent" && (c.params as any)?.type === "mousePressed");
    expect((pressed?.params as any)?.button).toBe("left");
  });

  it("clicks coordinates without a selector", async () => {
    const { cdpClick } = await import("./cdp_client.js");
    const { calls, send } = fakeSender();
    const pt = await cdpClick(send, { x: 5, y: 6 });
    expect(pt).toEqual({ x: 5, y: 6 });
    expect(calls.some((c) => (c.params as any)?.expression?.includes("getBoundingClientRect"))).toBe(false);
  });

  it("throws on a missing selector", async () => {
    const { resolveSelectorCenter } = await import("./cdp_client.js");
    const { send } = fakeSender(null);
    await expect(resolveSelectorCenter(send, ".nope")).rejects.toThrow("Element not found");
  });

  it("types atomically with one insertText plus optional enter", async () => {
    const { cdpTypeText } = await import("./cdp_client.js");
    const { calls, send } = fakeSender();
    await cdpTypeText(send, { selector: "input", text: "hi", pressEnter: true });
    const inserts = calls.filter((c) => c.method === "Input.insertText");
    expect(inserts).toHaveLength(1);
    expect((inserts[0].params as any)?.text).toBe("hi");
    // raw key events remain only for the Enter chord
    const keys = calls.filter((c) => c.method === "Input.dispatchKeyEvent");
    expect(keys.filter((c) => (c.params as any)?.type === "keyDown")).toHaveLength(0);
    expect(keys.filter((c) => (c.params as any)?.type === "keyUp")).toHaveLength(1);
    expect(keys.some((c) => (c.params as any)?.key === "Enter")).toBe(true);
  });

  it("delivers a representative string intact in one call (issue 1159)", async () => {
    const { cdpTypeText } = await import("./cdp_client.js");
    const { calls, send } = fakeSender();
    const text = "Hello, World! 123 @#é — quote: \"hi\"";
    await cdpTypeText(send, { text });
    const inserts = calls.filter((c) => c.method === "Input.insertText");
    expect(inserts).toHaveLength(1);
    expect((inserts[0].params as any)?.text).toBe(text);
    expect(calls.some((c) => c.method === "Input.dispatchKeyEvent")).toBe(false);
  });

  it("injection script is a single self-contained payload", async () => {
    const { CURSOR_INJECTION_SCRIPT } = await import("./cdp_client.js");
    expect(CURSOR_INJECTION_SCRIPT).toContain("__agent_cdp_cursor");
    expect(CURSOR_INJECTION_SCRIPT).not.toMatch(/'\s*'/);
  });
});
