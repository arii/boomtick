import re
import os
import json
import sys

def resolve_file_path(path):
    """Resolves path relative to current working directory or via filename lookup."""
    if not path:
        return None

    # 1. Direct check (if absolute and exists, we take it, but we prefer relative)
    if os.path.isabs(path) and os.path.exists(path):
         # If it's absolute but under current directory, make it relative
         try:
             rel = os.path.relpath(path)
             if not rel.startswith('..'):
                 return rel
         except ValueError:
             pass

    # 2. Try stripping leading common absolute paths (like /app/ or /workspace/)
    # We look for the first part that actually exists in the current directory relative to CWD
    parts = [p for p in path.split(os.sep) if p]
    for i in range(len(parts)):
        subpath = os.path.join(*parts[i:])
        if subpath and os.path.exists(subpath):
            return subpath

    # 3. Fallback to basename lookup in current directory (recursive)
    filename = os.path.basename(path)
    for root, dirs, files in os.walk('.'):
        if filename in files:
            found_path = os.path.join(root, filename)
            if found_path.startswith('./'):
                return found_path[2:]
            return found_path

    return None

def strip_ansi(text):
    """Strips ANSI color codes from string."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

class SignatureExtractor:
    """Extracts file, line, and error signature from logs."""

    # ESLint stylish: /app/src/App.tsx:10:5: 'unused' is defined but never used. [eslint/no-unused-vars]
    # ESLint compact: /app/src/App.tsx: line 10, col 5, Error - 'unused' is defined but never used. [eslint/no-unused-vars]
    ESLINT_PATTERN = re.compile(r'^(.*?):(\d+):(\d+): (.*) \[(.*)\]$')
    ESLINT_COMPACT_PATTERN = re.compile(r'^(.*?): line (\d+), col (\d+), (?:Error|Warning) - (.*) \[(.*)\]$')

    # TS example: src/App.tsx:10:5 - error TS2322: Type 'string' is not assignable to type 'number'.
    TS_PATTERN = re.compile(r'^(.*?):(\d+):(\d+) - error (TS\d+): (.*)$')

    # TS alternate: src/App.tsx(10,5): error TS2322: ...
    TS_ALT_PATTERN = re.compile(r'^(.*?)\((\d+),(\d+)\): error (TS\d+): (.*)$')

    @classmethod
    def extract(cls, log_line):
        log_line = strip_ansi(log_line.strip())

        # Try ESLint
        match = cls.ESLINT_PATTERN.match(log_line) or cls.ESLINT_COMPACT_PATTERN.match(log_line)
        if match:
            sig = match.group(5)
            if not sig.startswith('eslint/') and '/' not in sig:
                sig = f"eslint/{sig}"
            return {
                "file": match.group(1),
                "line": int(match.group(2)),
                "col": int(match.group(3)),
                "message": match.group(4),
                "signature": sig
            }

        # Try TS
        match = cls.TS_PATTERN.match(log_line)
        if match:
            return {
                "file": match.group(1),
                "line": int(match.group(2)),
                "col": int(match.group(3)),
                "message": match.group(5),
                "signature": f"ts/{match.group(4)[2:]}" # Normalize TS2322 to ts/2322
            }

        # Try TS Alt
        match = cls.TS_ALT_PATTERN.match(log_line)
        if match:
            return {
                "file": match.group(1),
                "line": int(match.group(2)),
                "col": int(match.group(3)),
                "message": match.group(5),
                "signature": f"ts/{match.group(4)[2:]}"
            }

        return None

class ASTContextualizer:
    """Extracts surrounding code block for a given line."""

    @staticmethod
    def extract_context(filepath, line_number, window=15):
        """
        Extracts a deterministic window of code around line_number.
        Uses a fixed window to avoid brittle indentation heuristics.
        """
        if not os.path.exists(filepath):
            return None

        try:
            with open(filepath, 'r') as f:
                lines = f.readlines()
        except Exception:
            return None

        if not lines:
            return None

        # Adjust to 0-indexed
        idx = line_number - 1
        if idx < 0 or idx >= len(lines):
            return None

        # Use a deterministic window
        start_idx = max(0, idx - window)
        end_idx = min(len(lines) - 1, idx + window)

        context_lines = lines[start_idx:end_idx+1]
        return "".join(context_lines)

class RAGPipeline:
    """Coordinates extraction, lookup, and prompt construction."""

    def __init__(self, knowledge_base_path=None):
        if knowledge_base_path is None:
            if os.path.exists(".agents/knowledge/errors.json"):
                knowledge_base_path = ".agents/knowledge/errors.json"
            else:
                knowledge_base_path = ".jules/knowledge/errors.json"
        self.knowledge_base_path = knowledge_base_path
        self.knowledge_base = self._load_kb()

    def _load_kb(self):
        if not os.path.exists(self.knowledge_base_path):
            return {}
        try:
            with open(self.knowledge_base_path, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"⚠️ Warning: Knowledge base JSON is invalid: {e}", file=sys.stderr)
            return {}
        except Exception as e:
            print(f"⚠️ Warning: Failed to load knowledge base: {e}", file=sys.stderr)
            return {}

    def generate_prompt(self, log_line):
        extracted = SignatureExtractor.extract(log_line)
        if not extracted:
            return None

        sig = extracted['signature']
        strategy_data = self.knowledge_base.get(sig, {})
        strategy = strategy_data.get('strategy', "Investigate the error and apply a fix based on common practices.")
        examples = strategy_data.get('examples', [])

        # Adjust file path for context extraction
        filepath = resolve_file_path(extracted['file'])
        context = ASTContextualizer.extract_context(filepath, extracted['line']) if filepath else None

        prompt = f"### Error Report\n"
        prompt += f"- **File**: `{extracted['file']}`\n"
        prompt += f"- **Line**: {extracted['line']}\n"
        prompt += f"- **Error**: `{extracted['signature']}`: {extracted['message']}\n\n"

        prompt += f"### Fix Strategy\n"
        prompt += f"{strategy}\n\n"

        if examples:
            prompt += "### Few-Shot Examples\n"
            for ex in examples:
                prompt += f"**Before:**\n```\n{ex['before']}\n```\n"
                prompt += f"**After:**\n```\n{ex['after']}\n```\n"
            prompt += "\n"

        if context:
            prompt += "### Code Context\n"
            prompt += f"```tsx\n{context}\n```\n"

        return prompt

if __name__ == "__main__":
    # Quick manual test
    test_logs = [
        "/app/src/App.tsx:10:5: 'unused' is defined but never used. [no-unused-vars]",
        "/app/src/App.tsx:11:5: Some hook error. [react-hooks/rules-of-hooks]",
        "src/App.tsx:10:5 - error TS2322: Type 'string' is not assignable to type 'number'.",
        "src/App.tsx(10,5): error TS2322: Type 'string' is not assignable to type 'number'."
    ]
    pipeline = RAGPipeline()
    for log in test_logs:
        print(f"--- Processing Log: {log} ---")
        prompt = pipeline.generate_prompt(log)
        if prompt:
            print(prompt)
        else:
            print("Failed to generate prompt.")
