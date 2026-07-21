# pylint: disable=global-statement,import-outside-toplevel,invalid-name,line-too-long,missing-docstring,redefined-outer-name,reimported,too-many-branches,too-many-locals,too-many-return-statements,too-many-statements,unused-argument
import json
import os
import re
import sys
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple, Type

import requests
from dev_tools.models import AIFullReview, AISynthesisReview, AIFileReview
from dev_tools.review_read_pass import parse_diff_into_file_chunks
from dev_tools.services.dependency_graph import DependencyGraph
from dev_tools.services.vector_store import VectorStore
from dev_tools.utils import (
    call_ai,
    clean_llm_output,
    ensure_dir,
    get_ai_model,
    get_ai_review_model,
    get_gemini_model,
    get_stack_versions,
    is_ai_available,
    log_error,
    log_info,
    log_warn,
)
from dev_tools.verify_versions import parse_diff, verify_changes
from pydantic import BaseModel, ValidationError

# Model used for per-file chunk review (code-aware, focused)
_REVIEW_MODEL = get_ai_review_model()

# Model used for final summary synthesis
_SYNTHESIS_MODEL = get_ai_model()

# Maximum retries for AI generation and parsing
_MAX_AI_RETRIES = 3

# Sleep time between retries
_RETRY_SLEEP_SECONDS = 1

# Combined review schema
_REVIEW_SCHEMA = AIFullReview.model_json_schema()

# Synthesis review schema
_SYNTHESIS_SCHEMA = AISynthesisReview.model_json_schema()


def validate_with_model(data: Any, model_class: Type[BaseModel]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Validates data against a Pydantic model and returns (parsed_dict, error_message)."""
    try:
        # Handle cases where data might be double-encoded or stringified
        if isinstance(data, str):
            try:
                data = json.loads(data)
                if isinstance(data, str):
                    data = json.loads(data)
            except json.JSONDecodeError:
                pass

        if not isinstance(data, dict):
            return None, f"Expected dictionary for validation, got {type(data).__name__}"

        parsed = model_class.model_validate(data)
        return parsed.model_dump(), None
    except ValidationError as e:
        # Extract specific error details from Pydantic
        errs = []
        for err in e.errors():
            loc = " -> ".join(str(x) for x in err.get("loc", []))
            msg = err.get("msg")
            errs.append(f"[{loc}]: {msg}")
        return None, "Validation failed:\n  " + "\n  ".join(errs)


_REVIEW_CONSTANTS_CACHE = None


def _get_review_prompt_constants() -> tuple[str, str, str]:
    global _REVIEW_CONSTANTS_CACHE
    if _REVIEW_CONSTANTS_CACHE is not None:
        return _REVIEW_CONSTANTS_CACHE

    try:
        import json

        from dev_tools.utils import resolve_resource_path

        resource_path = resolve_resource_path("prompt_constants.json")
        with open(resource_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        json_rules = data.get("STRICT_JSON_VERIFICATION", "")
        snippet_rules = data.get("SNIPPET_AND_VERIFICATION_RULES", "")
        common_rules = data.get("COMMON_REVIEW_GUIDELINES", "")

        _REVIEW_CONSTANTS_CACHE = (json_rules, snippet_rules, common_rules)
        return _REVIEW_CONSTANTS_CACHE
    except Exception as e:
        log_warn(f"Failed to load prompt_constants.json from resources: {e}")
        # Default fallback values to prevent empty constraints from degrading review quality
        default_json = "Strict JSON Verification:\n- Every finding MUST have an `id`, `file`, `issue`, and `status`."
        default_snippet = "Snippet rules:\n- STRICT SNIPPET RULE: Quote exact line from diff."
        default_common = "Review ONLY PR changes. Assume original code worked."
        _REVIEW_CONSTANTS_CACHE = (default_json, default_snippet, default_common)
        return _REVIEW_CONSTANTS_CACHE


class AIClient:
    def __init__(self, ai_model: Optional[str] = None):
        self.ai_model = ai_model or get_ai_model()
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY")

        self._dependency_graph: Optional[DependencyGraph] = None
        self._vector_store: Optional[VectorStore] = None

    @property
    def dependency_graph(self) -> DependencyGraph:
        if self._dependency_graph is None:
            self._dependency_graph = DependencyGraph()
        return self._dependency_graph

    @property
    def vector_store(self) -> VectorStore:
        if self._vector_store is None:
            self._vector_store = VectorStore()
        return self._vector_store

    def is_ai_available(self) -> bool:
        return is_ai_available()

    def call_ai(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_retries: int = 3,
        schema: Optional[Dict] = None,
    ) -> Optional[str]:
        return call_ai(prompt, model=model or self.ai_model, max_retries=max_retries, schema=schema)

    def call_gemini(self, prompt: str, schema: Optional[Dict] = None) -> Optional[str]:
        if not self.gemini_api_key:
            return None

        model_name = get_gemini_model()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        headers = {"Content-Type": "application/json", "x-goog-api-key": self.gemini_api_key}

        payload = {"contents": [{"parts": [{"text": prompt}]}]}

        if schema:
            payload["generationConfig"] = {
                "responseMimeType": "application/json",
                "responseSchema": schema,
            }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            res_data = response.json()
            if "candidates" in res_data and len(res_data["candidates"]) > 0:
                content = res_data["candidates"][0]["content"]["parts"][0]["text"]
                return content
            return None
        except Exception as e:
            log_warn(f"Gemini API call failed: {e}")
            return None

    def generate(self, prompt: str, schema: Optional[Dict] = None, model: Optional[str] = None) -> str:
        if self.is_ai_available():
            res = self.call_ai(prompt, model=model, schema=schema)
            if res:
                return res

        res = self.call_gemini(prompt, schema=schema)
        if res:
            return res

        raise EnvironmentError("No AI service available (GitHub Models, and Gemini failed or are unavailable).")

    def clean_llm_output(self, text: str) -> str:
        return clean_llm_output(text)

    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate the number of tokens in the given text using a character-count heuristic.
        Standard heuristic is 4 characters per token.
        """
        if not text:
            return 0
        return (len(text) + 3) // 4

    def resolve_file_conflicts(self, file_path: str) -> bool:
        if not os.path.exists(file_path):
            return False

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            if "<<<<<<<" not in content:
                return True

            # AI resolution mock mode
            if os.environ.get("AI_RESOLVE_MOCK", "false").lower() == "true":
                mock_pattern = r"<<<<<<<.*?\n(.*?)\n=======.*?\n>>>>>>>.*?\n"
                resolved = re.sub(mock_pattern, r"\1\n", content, flags=re.DOTALL)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(resolved)
                return True

            prompt = f"Resolve the Git merge conflicts in this code. Output ONLY the clean, merged code without markers or explanation.\n\nFILE CONTENT:\n{content}\n\nREPAIRED CONTENT:\n"

            raw_response = self.generate(prompt)
            if not raw_response:
                return False

            resolved = self.clean_llm_output(raw_response)

            if "<<<<<<<" in resolved:
                return False

            try:
                # Files that define runtime/dependency versions
                sensitive_files = [".nvmrc", ".node-version", "package.json", ".github/workflows/"]
                if any(sf in file_path for sf in sensitive_files):
                    # Synthesize a diff representing the new content to validate it against HEAD versions.
                    # We treat lines in the new file as additions to ensure the validator
                    # catches any version mentioned in the file that might be a downgrade from HEAD.
                    diff_lines = [f"+++ b/{file_path}"]
                    for line in resolved.splitlines():
                        line = line.strip()
                        # We only care about lines that look like version assignments/usage
                        if any(kw in line for kw in ["node", "pnpm", "uses:", "@v", "packageManager"]):
                            diff_lines.append(f"+{line}")

                    if len(diff_lines) > 1:
                        # Re-use the validation logic on the synthesized diff
                        findings = verify_changes(parse_diff("\n".join(diff_lines)))
                        if any(f["severity"] == "error" for f in findings):
                            log_error(
                                f"AI-generated resolution for {file_path} contains version violations: {findings}"
                            )
                            # Re-try or block to prevent regression
                            return False
            except Exception as e:
                log_warn(f"Failed to post-process AI resolution for {file_path}: {e}")

            from dev_tools.utils import safe_write_file

            if not resolved.endswith("\n"):
                resolved += "\n"
            safe_write_file(file_path, resolved)

            return True
        except Exception:
            return False

    # ── Single-pass review pipeline ───────────────────────────────────────────

    def generate_code_review(self, pr: Dict, diff: str) -> Dict:
        """
        Single-pass AI review pipeline leveraging large context windows.
        Skips images, lock files, generated files, and build artefacts.
        """

        pr_num = pr.get("number", "unknown")
        pr_title = pr.get("title", "")
        checks = pr.get("checkResults", [])
        checks_summary = (
            "\n".join(f"- {c.get('name')}: {c.get('status')} ({c.get('conclusion', 'Pending')})" for c in checks)
            if checks
            else "No checks found."
        )

        ci_failures = [c for c in checks if c.get("conclusion") == "failure"]
        has_ci_failures = bool(ci_failures)
        failing_names = ", ".join(c.get("name", "?") for c in ci_failures) if ci_failures else "none"

        # ── Diagnostics header ────────────────────────────────────────────────
        ai_ok = self.is_ai_available()
        chunks = parse_diff_into_file_chunks(diff)
        skipped = [c for c in chunks if c["skip"]]
        reviewable = [c for c in chunks if not c["skip"]]

        _skipped_names = sorted(set(c["file"] for c in skipped))
        _skipped_preview = ", ".join(_skipped_names[:5]) + ("..." if len(_skipped_names) > 5 else "")

        log_info(f"""
{'='*60}
🔍 PR #{pr_num} – Unified Review Diagnostics
{'='*60}
  AI available : {'✅ YES' if ai_ok else '❌ NO'}
  Review model : {_REVIEW_MODEL}
  Diff size    : {len(diff):,} chars
  CI failures  : {failing_names}

📂 Files in diff   : {len(chunks)} total
   Reviewable      : {len(reviewable)} chunks across {len(set(c['file'] for c in reviewable))} files
   Skipped         : {len(skipped)} ({_skipped_preview})
""")

        file_reviews: List[Dict] = []

        if not reviewable:
            final = {
                "reviewComment": f"Automated review of PR #{pr_num}.\n\nNo reviewable files found in the diff.",
                "labels": [],
                "recommendation": "Approved" if not has_ci_failures else "Not Approved",
            }
            self._write_review_file(pr_num, pr, final, chunks, [])
            return final

        # Combine diffs up to a reasonable limit (e.g. 100k chars for standard models)
        MAX_COMBINED_CHARS = 100_000
        combined_diff = ""
        is_truncated = False
        for chunk in reviewable:
            if len(combined_diff) + len(chunk["diff_text"]) > MAX_COMBINED_CHARS:
                combined_diff += "\n\n... (Diff truncated due to size limits)"
                is_truncated = True
                break
            combined_diff += f"\n\n{chunk['diff_text']}"

        # Determine whether to use piecemeal review aggregator or single-pass review using token estimation
        estimated_tokens = self._estimate_tokens(combined_diff)
        use_piecemeal = (estimated_tokens > 25000) or (os.environ.get("FORCE_PIECEMEAL_REVIEW", "false").lower() == "true")

        if use_piecemeal:
            return self._process_piecemeal_review(
                reviewable,
                pr_num,
                pr_title,
                checks_summary,
                chunks,
                pr,
                has_ci_failures,
                ci_failures,
                failing_names,
                estimated_tokens,
            )

        # Single-pass fallback
        truncation_note = ""
        json_rules, snippet_rules, _COMMON_REVIEW_GUIDELINES = _get_review_prompt_constants()
        if is_truncated:
            truncation_note = "\nNOTE: This diff is TRUNCATED. If you need more context to be certain of an issue, state what you are missing instead of speculating.\n"

        prompt = (
            f"Review PR: {pr_title}. CI: {checks_summary}\n\n"
            f"{_COMMON_REVIEW_GUIDELINES}\n\n"
            "ORDER: Correctness, Security (new input/auth only), Crashes, Data Integrity, Performance, Maintainability.\n"
            "SEVERITY: error (blocking, high confidence only), warn, info. Include 'confidence' (high/medium/low).\n"
            f"Rules:\n"
            f"- Flag ONLY real problems: bugs, type unsafety, broken logic, design rule violations.\n"
            f"{snippet_rules}\n\n"
            f"{json_rules}\n\n"
            f'- Use severity "error" for blocking issues, "warn" for improvements, "info" for nits.\n'
            f'- For file verdicts, set to "ok" (no issues), "needs_changes" (warn/info only), or "blocking" (any error).\n'
            f"- Provide an overall `reviewComment` summarizing the review.\n"
            f'- Suggest 1-3 `labels` (e.g. "needs-changes", "lgtm", "ci-failing").\n'
            f'- Set overall `recommendation` to EXACTLY ONE of: "Approved", "Approved with Minor Changes", or "Not Approved".\n'
            "OUTPUT: Valid JSON. Counterexamples required for errors.\n"
            "JSON MUST be inside a <findings> tag.\n\n"
            f"{truncation_note}Diff:\n{combined_diff}"
        )

        t0 = time.time()
        print(
            f"🤖 Requesting AI review for {len(reviewable)} chunks ...",
            end="",
            flush=True,
            file=sys.stderr,
        )

        raw = None
        file_reviews = []
        parsed = None

        # Retry loop for generation and parsing
        for attempt in range(_MAX_AI_RETRIES):
            try:
                raw = call_ai(prompt, model=_REVIEW_MODEL, schema=_REVIEW_SCHEMA, max_retries=1)
                if not raw:
                    continue

                cleaned = clean_llm_output(raw)

                # Robust extraction fallback for mixed/malformed model output
                candidate = cleaned
                first_brace = candidate.find("{")
                first_bracket = candidate.find("[")
                last_brace = candidate.rfind("}")
                last_bracket = candidate.rfind("]")

                start = -1
                end = -1
                if first_brace != -1 and (first_bracket == -1 or first_brace < first_bracket):
                    start, end = first_brace, last_brace
                elif first_bracket != -1:
                    start, end = first_bracket, last_bracket

                if start != -1 and end != -1 and end > start:
                    json_candidate = candidate[start : end + 1]
                    try:
                        temp_parsed = json.loads(json_candidate)
                        cleaned = json.dumps(temp_parsed)
                    except json.JSONDecodeError:
                        pass

                parsed, err = validate_with_model(cleaned, AIFullReview)
                if err or parsed is None:
                    raise ValueError(err or "Validation failed")

                if isinstance(parsed, dict):
                    break  # Success
            except Exception as e:
                log_warn(f"AI review attempt {attempt+1} failed: {e}")
                time.sleep(1)

        elapsed = time.time() - t0

        if not parsed:
            print(f" ❌ failed to get valid response ({elapsed:.1f}s)", flush=True, file=sys.stderr)
            final = {
                "reviewComment": f"Automated review of PR #{pr_num}.\n\nFailed to get a parseable response from AI after retries.",
                "labels": ["needs-changes"],
                "recommendation": "Not Approved",
            }
        else:
            file_reviews = parsed.get("file_reviews", [])
            final = {
                "reviewComment": str(parsed.get("reviewComment", f"Automated review of PR #{pr_num}.")),
                "labels": list(parsed.get("labels", [])),
                "recommendation": str(parsed.get("recommendation", "Unknown")),
            }
            print(f" ✅ done ({elapsed:.1f}s)", flush=True, file=sys.stderr)

        # CI guard: never approve if checks are failing
        if has_ci_failures and final.get("recommendation") == "Approved":
            final["recommendation"] = "Not Approved"
            final["reviewComment"] = f"CI checks are failing ({failing_names}). Recommendation downgraded.\n\n" + (final.get("reviewComment") or "")

        self._write_review_file(pr_num, pr, final, chunks, file_reviews)
        return final

    def _process_piecemeal_review(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        reviewable: List[Dict],
        pr_num: Any,
        pr_title: str,
        checks_summary: str,
        chunks: List[Dict],
        pr: Dict,
        has_ci_failures: bool,
        ci_failures: List[Dict],
        failing_names: str,
        estimated_tokens: int,
    ) -> Dict:
        """Process code review by chunks and aggregate individual results into a synthesized verdict."""
        log_info(f"🧱 PR Context Aggregator: Large PR (estimated {estimated_tokens} tokens) or forced mode detected. Running piecemeal review across {len(reviewable)} chunks.")
        file_reviews = []
        completed = 0

        for chunk_data in reviewable:
            chunk_prompt = self._build_chunk_prompt(chunk_data, pr_title, checks_summary)
            parsed_chunk = None

            for attempt in range(_MAX_AI_RETRIES):
                try:
                    raw_chunk = self.call_ai(chunk_prompt, model=_REVIEW_MODEL, schema=AIFileReview.model_json_schema(), max_retries=1)
                    if not raw_chunk:
                        continue
                    cleaned_chunk = self.clean_llm_output(raw_chunk)

                    parsed_chunk, err = validate_with_model(cleaned_chunk, AIFileReview)
                    if err or parsed_chunk is None:
                        raise ValueError(err or "Validation failed")

                    break  # Successfully parsed and validated
                except Exception as e:
                    log_warn(f"Chunk review attempt {attempt+1} failed for {chunk_data['file']} chunk {chunk_data.get('chunk_index', 0)}: {e}")
                    time.sleep(_RETRY_SLEEP_SECONDS)

            if not parsed_chunk:
                parsed_chunk = {
                    "file": chunk_data["file"],
                    "issues": [],
                    "verdict": "error",
                    "error": f"Failed to get a parseable review for chunk {chunk_data.get('chunk_index', 0)} after retries.",
                    "chunk_index": chunk_data.get("chunk_index", 0)
                }
            else:
                parsed_chunk["chunk_index"] = chunk_data.get("chunk_index", 0)

            file_reviews.append(parsed_chunk)
            completed += 1
            self._write_progress_snapshot(pr_num, reviewable, file_reviews, completed, "")

        # Synthesize all chunk reviews into a consolidated final review
        final = self._synthesize_review(file_reviews, pr_num, pr_title, has_ci_failures, ci_failures)

        # CI guard: never approve if checks are failing
        if has_ci_failures and final.get("recommendation") == "Approved":
            final["recommendation"] = "Not Approved"
            final_comment = final.get("reviewComment") or ""
            final["reviewComment"] = f"CI checks are failing ({failing_names}). Recommendation downgraded.\n\n{final_comment}"

        self._write_review_file(pr_num, pr, final, chunks, file_reviews)
        return final

    def _get_context_for_chunk(self, chunk: Dict) -> str:
        """Retrieves dependency and semantic context for a code chunk."""
        filepath = str(chunk.get("file", ""))
        context_parts = []

        # 1. Dependency Context
        deps = self.dependency_graph.get_dependencies(filepath)
        dependents = self.dependency_graph.get_dependents(filepath)
        if deps or dependents:
            context_parts.append("### Dependency Context")
            if deps:
                context_parts.append(f"- Dependencies: {', '.join(deps[:10])}")
            if dependents:
                context_parts.append(f"- Impacted files (dependents): {', '.join(dependents[:10])}")

        # 2. Semantic Context
        try:
            if not self.vector_store.is_available():
                return "\n".join(context_parts)

            diff_text = chunk.get("diff_text") or chunk.get("diff") or ""
            if not diff_text:
                return "\n".join(context_parts)

            semantic_results = self.vector_store.query(diff_text, n_results=3)
            if semantic_results:
                context_parts.append("\n### Semantically Related Code")
                for res in semantic_results:
                    path = res["metadata"].get("path", "unknown")
                    if path != filepath:
                        context_parts.append(f"#### From {path}:")
                        context_parts.append(f"```\n{res['document'][:500]}\n```")
        except Exception as e:
            print(f"Error searching vector store: {e}", file=sys.stderr)  # Log failure if not indexed

        return "\n".join(context_parts)

    def _build_chunk_prompt(self, chunk: Dict, pr_title: str, checks_summary: str) -> str:
        trunc_note = "\n(Note: diff was truncated to fit context window)" if chunk.get("truncated") else ""

        context = self._get_context_for_chunk(chunk)
        context_section = f"\n\n## Repository Context\n{context}" if context else ""

        stack_versions = get_stack_versions(fetch_latest=True)
        versions_block = "\n".join([f"- {k}: {v}" for k, v in stack_versions.items()])

        json_rules, snippet_rules, _COMMON_REVIEW_GUIDELINES = _get_review_prompt_constants()
        return (
            f"Review {chunk['file']}. PR: {pr_title}. CI: {checks_summary}\n"
            f"VERSIONS: {versions_block}\n{context_section}\n\n"
            f"{_COMMON_REVIEW_GUIDELINES}\n\n"
            f"Rules:\n"
            f'- DO NOT suggest downgrading any versions listed in the "Current Stack Versions" section.\n'
            f"- Flag ONLY real problems: bugs, type unsafety, broken logic, design rule violations.\n"
            f"{snippet_rules}\n\n"
            f"{json_rules}\n\n"
            f'- Use severity "error" for blocking issues, "warn" for improvements, "info" for nits.\n'
            f'- Set verdict to "ok" (no issues), "needs_changes" (warn/info only), or "blocking" (any error).\n'
            "OUTPUT: Valid JSON. Counterexamples required for errors.\n"
            "JSON MUST be inside a <findings> tag.\n\n"
            f"Diff:{trunc_note}\n{chunk['diff_text']}"
        )

    def _write_progress_snapshot(
        self,
        pr_num: Any,
        reviewable: List[Dict],
        file_reviews: List[Dict],
        completed: int,
        cache_dir: str,
    ) -> None:
        """Write a live progress file after each chunk so intermediate results are visible."""
        output_dir = ensure_dir("logs", "reviews")
        progress_path = os.path.join(output_dir, f"pr-review-{pr_num}-progress.md")

        total = len(reviewable)
        pct = int(completed / total * 100) if total else 0
        verdict_icon = {
            "ok": "✅",
            "needs_changes": "⚠️",
            "blocking": "🚫",
            "error": "❓",
            "parse_error": "❓",
        }

        lines = [
            f"# PR #{pr_num} – Review In Progress ({completed}/{total} files, {pct}%)",
            "",
            f"_Last updated: {time.strftime('%Y-%m-%d %H:%M:%S')}_",
            "",
            "## Completed Files",
            "",
            "| # | File | Added Lines | Issues | Verdict |",
            "|---|---|---|---|---|",
        ]

        for idx, fr in enumerate(file_reviews, 1):
            chunk = next(
                (c for c in reviewable if c["file"] == fr["file"] and c["chunk_index"] == fr.get("chunk_index", 0)),
                {},
            )
            added = chunk.get("added_lines", "?")
            issues = len(fr.get("issues", []))
            v = fr.get("verdict", "?")
            icon = verdict_icon.get(v, "❓")
            lines.append(f"| {idx} | `{fr['file']}` | {added} | {issues} | {icon} {v} |")

        # Pending files
        completed_files = {fr["file"] for fr in file_reviews}
        pending = [c for c in reviewable if c["file"] not in completed_files]
        if pending:
            lines += ["", "## Pending Files", ""]
            for c in pending:
                lines.append(f"- `{c['file']}` ({c['added_lines']} added lines)")

        # Findings detail for completed files
        lines += ["", "## Findings Detail", ""]
        for fr in file_reviews:
            issues = fr.get("issues", [])
            v = fr.get("verdict", "?")
            icon = verdict_icon.get(v, "❓")
            lines.append(f"### {icon} `{fr['file']}` — {v}")
            if issues:
                for issue in issues:
                    sev = issue.get("severity", "?")
                    ln = issue.get("line", "?")
                    comment = issue.get("comment", "")
                    lines.append(f"- **[{sev}]** line {ln}: {comment}")
            else:
                err = fr.get("error") or fr.get("raw")
                lines.append(f"  _{err or 'No issues found.'}_")
            lines.append("")

        try:
            with open(progress_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except Exception as e:
            log_warn(f"Could not write progress file: {e}")

    def _synthesize_review(
        self,
        file_reviews: List[Dict],
        pr_num: Any,
        pr_title: str,
        has_ci_failures: bool,
        ci_failures: List[Dict],
    ) -> Dict:
        """Call the lighter gpt-4o model to produce the final verdict from structured per-chunk data."""
        total_issues = sum(len(fr.get("issues", [])) for fr in file_reviews if isinstance(fr, dict))
        blocking_files = [
            fr.get("file", "unknown") for fr in file_reviews if isinstance(fr, dict) and fr.get("verdict") == "blocking"
        ]
        error_files = [
            fr.get("file", "unknown")
            for fr in file_reviews
            if isinstance(fr, dict) and fr.get("verdict") in ("error", "parse_error")
        ]
        needs_files = [
            fr.get("file", "unknown")
            for fr in file_reviews
            if isinstance(fr, dict) and fr.get("verdict") == "needs_changes"
        ]
        ok_files = [
            fr.get("file", "unknown") for fr in file_reviews if isinstance(fr, dict) and fr.get("verdict") == "ok"
        ]

        # Build a compact findings summary (keep prompt small)
        findings_lines = []
        for fr in file_reviews:
            if not isinstance(fr, dict):
                continue
            for issue in fr.get("issues", []):
                if not isinstance(issue, dict):
                    continue
                findings_lines.append(
                    f'  - {fr.get("file", "?")}:{issue.get("line", "?")} [{issue.get("severity", "?")}] {issue.get("comment", "")}'
                )
        findings_str = "\n".join(findings_lines[:60])  # cap at 60 lines
        if len(findings_lines) > 60:
            findings_str += f"\n  ... ({len(findings_lines) - 60} more issues omitted)"

        ci_note = ""
        if has_ci_failures:
            ci_note = (
                f"\nCI FAILURES: {', '.join(c.get('name', '?') for c in ci_failures)} – must NOT recommend Approved.\n"
            )

        prompt = (
            f'You are summarising a code review for PR #{pr_num} – "{pr_title}".\n'
            f"{ci_note}\n"
            f"Per-file results:\n"
            f"  Blocking : {blocking_files or 'none'}\n"
            f"  Needs changes: {needs_files or 'none'}\n"
            f"  OK       : {ok_files or 'none'}\n"
            f"  Errors (could not review): {error_files or 'none'}\n"
            f"Total issues found: {total_issues}\n\n"
            f"Issue details:\n{findings_str if findings_str else '  (none)'}\n\n"
            f"Format your response as a standard Markdown report followed by a metadata JSON block.\n\n"
            f"The Markdown report should summarize the findings concisely.\n\n"
            f"The JSON block at the bottom MUST follow this schema:\n"
            f"{{\n"
            f'  "recommendation": "Approved | Approved with Minor Changes | Not Approved",\n'
            f'  "labels": ["lgtm", "needs-changes", ...],\n'
            f'  "reviewComment": "Concise summary for the body"\n'
            f"}}\n"
        )

        raw = None
        res = None
        for attempt in range(_MAX_AI_RETRIES):
            try:
                # We don't use strict schema mode here because we want mixed markdown + json
                raw = call_ai(prompt, model=_SYNTHESIS_MODEL, max_retries=1)
                if not raw:
                    continue

                cleaned = clean_llm_output(raw)
                res, err = validate_with_model(cleaned, AISynthesisReview)
                if err or res is None:
                    raise ValueError(err or "Validation failed")

                if isinstance(res, dict):
                    break  # Success
            except Exception as e:
                log_warn(f"Synthesis attempt {attempt+1} failed: {e}")
                time.sleep(1)

        if not res:
            # Fallback: construct a minimal result from the structured data
            if blocking_files:
                rec = "Not Approved"
            elif needs_files:
                rec = "Approved with Minor Changes"
            else:
                rec = "Approved"
            return {
                "reviewComment": (
                    f"Automated review of PR #{pr_num}.\n\n"
                    f"Blocking files: {blocking_files or 'none'}\n"
                    f"Files needing changes: {needs_files or 'none'}\n"
                    f"Total issues: {total_issues}\n\n"
                    f"(AI service returned no response; verdict derived from per-file data.)"
                ),
                "labels": ["needs-changes"] if rec != "Approved" else ["lgtm"],
                "recommendation": rec,
            }

        return res

    # ── Output file ───────────────────────────────────────────────────────────

    def _write_review_file(
        self,
        pr_num: Any,
        pr: Dict,
        review: Dict,
        chunks: List[Dict],
        file_reviews: List[Dict],
    ) -> None:
        """Populate and persist the review template with AI-generated content."""
        head_sha = pr.get("head", {}).get("sha", "unknown")
        check_results = pr.get("checkResults", [])
        failed_checks = [c.get("name") for c in check_results if c.get("conclusion") == "failure"]
        detected_errors_raw = pr.get("structuredFailures", [])

        failed_checks_str = "\n".join(f"  - {c}" for c in failed_checks) if failed_checks else "_None_"
        detected_errors_str = (
            "\n".join(
                f"  - `{e.get('file', '?')}:{e.get('line', '?')}` {e.get('message', '')}" for e in detected_errors_raw
            )
            if detected_errors_raw
            else "_None detected by parser._"
        )

        recommendation = review.get("recommendation", "Unknown")
        review_comment = review.get("reviewComment", "")
        labels = review.get("labels", [])
        labels_str = ", ".join(labels) if labels else "_None_"

        # Per-file findings table
        file_data: Dict[str, Dict] = defaultdict(lambda: {"added_lines": 0, "issues": [], "verdict": "ok"})
        for fr in file_reviews:
            if not isinstance(fr, dict):
                continue
            f = fr.get("file")
            if not f:
                continue
            issues = fr.get("issues", [])
            if isinstance(issues, list):
                file_data[f]["issues"].extend([i for i in issues if isinstance(i, dict)])

            # worst verdict wins: blocking > needs_changes > ok
            _rank = {"blocking": 3, "needs_changes": 2, "ok": 1, "error": 0, "parse_error": 0}
            verdict = fr.get("verdict", "ok")
            if not isinstance(verdict, str):
                verdict = str(verdict)
            if _rank.get(verdict, 0) > _rank.get(file_data[f]["verdict"], 0):
                file_data[f]["verdict"] = verdict
        for chunk in chunks:
            if not chunk["skip"]:
                file_data[chunk["file"]]["added_lines"] += chunk["added_lines"]

        table_rows = []
        for filepath, data in sorted(file_data.items()):
            issue_count = len(data["issues"])
            verdict_icon = {"ok": "✅", "needs_changes": "⚠️", "blocking": "🚫"}.get(data["verdict"], "❓")
            table_rows.append(
                f"| `{filepath}` | {data['added_lines']} | {issue_count} | {verdict_icon} {data['verdict']} |"
            )

        skipped_files = sorted(set(c["file"] for c in chunks if c["skip"]))
        skipped_str = ", ".join(f"`{f}`" for f in skipped_files) if skipped_files else "_None_"

        per_file_table = (
            ("| File | Lines Added | Issues | Verdict |\n" "|---|---|---|---|\n" + "\n".join(table_rows))
            if table_rows
            else "_No files reviewed._"
        )

        # Build inline comments JSON block
        all_issues: List[Dict[str, Any]] = []
        for fr in file_reviews:
            if not isinstance(fr, dict):
                continue
            issues = fr.get("issues", [])
            if not isinstance(issues, list):
                continue
            for issue in issues:
                if not isinstance(issue, dict):
                    continue
                conf = str(issue.get("confidence", "high")).upper()
                # Support both 'issue' and 'comment' fields from the model
                issue_description = str(issue.get("issue") or issue.get("comment") or "")
                all_issues.append(
                    {
                        "path": str(fr.get("file", "unknown")),
                        "line": issue.get("line", 1),
                        "body": f"[{issue.get('severity', '?')}] (Confidence: {conf}) {issue_description}",
                    }
                )

        metadata_json = json.dumps(
            {"recommendation": recommendation, "labels": labels, "comments": all_issues}, indent=2
        )

        content = f"""# PR Review: #{pr_num}

## Context

- **Last Commit Tracked (SHA):** {head_sha}
- **Labels:** {labels_str}
- **Recommendation:** {recommendation}

## Audit Checklist

For EVERY changed file, verify against these standards. Mark as `- [x]` when verified.

- [ ] Dead abstractions: No new class, context, or hook that a simpler primitive handles.
- [ ] Unnecessary indirection: No layer of wrapping where a direct function call suffices.
- [ ] Responsibility creep: Component does not take on state/logic belonging in parent/hook.
- [ ] Import bloat: No unnecessary `import React from 'react'` (React 17+).
- [ ] Token compliance: Uses established design tokens (no raw Tailwind values or inline styles).
- [ ] Audit ratio: If > 100 lines added, identified at least 10 lines to refactor/remove.

## Per-File Findings

{per_file_table}

_Skipped ({len(skipped_files)} files): {skipped_str}_

## CI Log Triage

(Populated if CI failures detected)
- **Failed Checks:**
{failed_checks_str}
- **Detected Errors:**
{detected_errors_str}
- **Root Cause Analysis:**
- **Remediation Steps:**

## AI Review Comment

{review_comment}

## Output JSON

Provide your metadata in the JSON block below. The review body is extracted from the Markdown content above.
DO NOT REMOVE THE BACKTICKS.

```json
{metadata_json}
```
"""
        output_dir = ensure_dir("logs", "reviews")
        output_path = os.path.join(output_dir, f"pr-review-{pr_num}.md")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        log_info(f"📝 Review written to: {output_path}")
