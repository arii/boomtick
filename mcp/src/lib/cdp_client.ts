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
