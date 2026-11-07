import { runTDCli, type TDCliResponse } from "./tdCli.js";

export interface VisualDiffSummary {
  reachable: boolean;
  url: string;
  mismatch_percentage: number;
  dom_node_count: number;
  interactive_elements: number;
  screenshot_path: string | null;
  error?: string | null;
}

export interface ImpactVisualResult {
  passed: boolean;
  ui_changed: boolean;
  visual_diff: VisualDiffSummary | null;
  error?: string;
  raw: TDCliResponse;
}

/**
 * Remote-CDP visual/DOM audit through the single deterministic engine:
 * shells out to `td audit-impact --json` (Python `browser_cdp.py`
 * connects over CDP to browserless; no local Chrome is ever launched)
 * and returns the typed `visual_diff` payload.
 */
export async function getVisualDiff(
  worktreePath: string,
  previewUrl?: string,
): Promise<ImpactVisualResult> {
  const args = ["audit-impact", "--worktree", worktreePath];
  if (previewUrl) {
    args.push("--preview-url", previewUrl);
  }
  args.push("--json");
  const raw = await runTDCli(args, "capture visual diff");
  return {
    passed: raw.passed === true,
    ui_changed: raw.ui_changed === true,
    visual_diff: (raw.visual_diff as VisualDiffSummary | null) ?? null,
    error: typeof raw.error === "string" ? raw.error : undefined,
    raw,
  };
}

export interface CdpPoint {
  x: number;
  y: number;
}

export type CdpSender = (
  method: string,
  params?: Record<string, unknown>,
) => Promise<any>;

export const CURSOR_INJECTION_SCRIPT = [
  "(() => {",
  "  if (window.__agentCursorInstalled) return;",
  "  window.__agentCursorInstalled = true;",
  "  const cursor = document.createElement('div');",
  "  cursor.id = '__agent_cdp_cursor';",
  "  cursor.style.cssText = 'position:fixed;top:0;left:0;width:18px;height:18px;' +",
  "    'border-radius:50%;background:rgba(255,59,48,0.85);border:2px solid #fff;' +",
  "    'box-shadow:0 0 8px rgba(0,0,0,0.6);pointer-events:none;z-index:2147483647;' +",
  "    'transform:translate(-50%,-50%);transition:top 0.08s,left 0.08s;';",
  "  document.documentElement.appendChild(cursor);",
  "  window.__moveAgentCursor = (x, y) => {",
  "    const el = document.getElementById('__agent_cdp_cursor');",
  "    if (el) { el.style.left = x + 'px'; el.style.top = y + 'px'; }",
  "  };",
  "})();",
].join("\n");

export function selectorCenterScript(selector: string): string {
  return (
    "(() => {" +
    ` const el = document.querySelector(${JSON.stringify(selector)});` +
    " if (!el) return null;" +
    " el.scrollIntoView({block: 'center', inline: 'center'});" +
    " const rect = el.getBoundingClientRect();" +
    " return { x: Math.round(rect.left + rect.width / 2)," +
    " y: Math.round(rect.top + rect.height / 2) };" +
    "})()"
  );
}

export async function ensureCursorOverlay(sendCdp: CdpSender): Promise<void> {
  await sendCdp("Page.enable");
  await sendCdp("Runtime.enable");
  await sendCdp("Page.addScriptToEvaluateOnNewDocument", {
    source: CURSOR_INJECTION_SCRIPT,
  });
  await sendCdp("Runtime.evaluate", { expression: CURSOR_INJECTION_SCRIPT });
}

export async function resolveSelectorCenter(
  sendCdp: CdpSender,
  selector: string,
): Promise<CdpPoint> {
  const { result } = await sendCdp("Runtime.evaluate", {
    expression: selectorCenterScript(selector),
    returnByValue: true,
  });
  if (!result?.value) {
    throw new Error(`Element not found for selector: ${selector}`);
  }
  return result.value as CdpPoint;
}

export async function cdpClick(
  sendCdp: CdpSender,
  target: { selector?: string; x?: number; y?: number },
): Promise<CdpPoint> {
  await ensureCursorOverlay(sendCdp);
  const pt: CdpPoint = target.selector
    ? await resolveSelectorCenter(sendCdp, target.selector)
    : { x: target.x ?? 0, y: target.y ?? 0 };
  await sendCdp("Runtime.evaluate", {
    expression: `window.__moveAgentCursor && window.__moveAgentCursor(${pt.x}, ${pt.y})`,
  });
  await sendCdp("Input.dispatchMouseEvent", { type: "mouseMoved", x: pt.x, y: pt.y });
  await sendCdp("Input.dispatchMouseEvent", {
    type: "mousePressed", x: pt.x, y: pt.y, button: "left", clickCount: 1,
  });
  await sendCdp("Input.dispatchMouseEvent", {
    type: "mouseReleased", x: pt.x, y: pt.y, button: "left", clickCount: 1,
  });
  return pt;
}

export async function cdpTypeText(
  sendCdp: CdpSender,
  options: { selector?: string; text: string; clearFirst?: boolean; pressEnter?: boolean },
): Promise<void> {
  if (options.selector) {
    await cdpClick(sendCdp, { selector: options.selector });
    if (options.clearFirst !== false) {
      await sendCdp("Runtime.evaluate", {
        expression:
          "(() => {" +
          ` const el = document.querySelector(${JSON.stringify(options.selector)});` +
          " if (el && 'value' in el) {" +
          " el.value = '';" +
          " el.dispatchEvent(new Event('input', {bubbles: true}));" +
          " }" +
          "})()",
      });
    }
  }
  // Atomic text input (issue #1159): one insertText call delivers the
  // whole string — the old per-character keyDown/keyUp loop dropped
  // chars and multiplied round trips. Raw key events remain only for
  // the Enter chord below.
  if (options.text) {
    await sendCdp("Input.insertText", { text: options.text });
  }
  if (options.pressEnter) {
    await sendCdp("Input.dispatchKeyEvent", {
      type: "rawKeyDown", windowsVirtualKeyCode: 13, key: "Enter", code: "Enter",
    });
    await sendCdp("Input.dispatchKeyEvent", {
      type: "keyUp", windowsVirtualKeyCode: 13, key: "Enter", code: "Enter",
    });
  }
}
