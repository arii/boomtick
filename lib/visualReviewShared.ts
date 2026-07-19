import { VisualRouteSummary } from './visualReviewTypes';

export function buildPreviousFindingsPrompt(summary: VisualRouteSummary): { type: string; text: string } {
  const findingsStr = summary.previousFindings!
    .map(f => {
      let line = `- [${f.id}] ${f.issue} (Status: ${f.status})`;
      if (f.fixSummary) {
        line += `\n   → ${f.fixSummary}`;
      }
      return line;
    })
    .join('\n');

  return {
    type: 'text',
    text: `PREVIOUS REVIEW ROUND FINDINGS FOR THIS ROUTE:\n${findingsStr}\n\nYour job:\n- Confirm THIS issue is resolved before raising anything new.\n- Only raise a NEW issue if it is unrelated to anything already addressed, or if the fix for a previous issue introduced a new problem.\n- Do not re-open a resolved issue under a different framing.`
  };
}

export function buildFindingsFormatPrompt(route: string): { type: string; text: string } {
  return {
    type: 'text',
    text: `You MUST also provide a structured JSON summary of the findings (both old and new) for this route at the end of your response, inside a <findings> tag:\n<findings>\n{\n  "findings": [\n    {\n      "id": "finding-1",\n      "route": "${route}",\n      "issue": "Brief description of the issue",\n      "status": "resolved",\n      "fixSummary": "Brief summary of how it was addressed"\n    }\n  ]\n}\n</findings>`
  };
}
