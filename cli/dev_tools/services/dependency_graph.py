# pylint: disable=missing-docstring,raise-missing-from,subprocess-run-check
import json
import os
import subprocess
from typing import Dict, List, Set

from dev_tools.utils import CLIError, log_error, log_warn


class DependencyGraph:
    def __init__(self, root_dir: str = "."):
        self.root_dir = root_dir
        self.graph: Dict[str, List[Dict]] = {}
        self.reverse_graph: Dict[str, List[str]] = {}
        self._load_graph()

    def _load_graph(self):
        """Loads the dependency graph using dependency-cruiser."""
        try:
            # Check if we have a cached graph first (optional, but good for performance)
            cache_path = os.path.join(self.root_dir, "artifacts", "dependency-graph.json")
            if os.path.exists(cache_path):
                with open(cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                depcruise_config = os.path.join(self.root_dir, ".dependency-cruiser.config.mjs")
                tsconfig = os.path.join(self.root_dir, "tsconfig.app.json")

                if not os.path.exists(depcruise_config) or not os.path.exists(tsconfig):
                    log_warn(f"Missing {depcruise_config} or {tsconfig}. Dependency graph will be empty.")
                    self.graph = {}
                    self.reverse_graph = {}
                    return

                # Run dependency-cruiser
                cmd = [
                    "pnpm",
                    "exec",
                    "depcruise",
                    "src",
                    "--config",
                    ".dependency-cruiser.config.mjs",
                    "--ts-config",
                    "tsconfig.app.json",
                    "--output-type",
                    "json",
                ]
                try:
                    # Explicitly check for pnpm availability
                    subprocess.run(["pnpm", "--version"], capture_output=True, check=True)

                    result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.root_dir)
                    if result.returncode != 0:
                        log_error(f"dependency-cruiser failed (exit {result.returncode}): {result.stderr}")
                        raise CLIError(f"dependency-cruiser failed: {result.stderr}")

                    try:
                        data = json.loads(result.stdout)
                    except json.JSONDecodeError as e:
                        log_error(f"Failed to parse dependency-cruiser output: {e}\nRaw output: {result.stdout}")
                        raise CLIError(f"Failed to parse dependency-cruiser output: {e}")
                except (FileNotFoundError, subprocess.CalledProcessError) as e:
                    log_error(f"pnpm or depcruise not found or failed: {e}")
                    raise CLIError("pnpm or depcruise not found. Ensure dependencies are installed.")

                if data and data.get("modules"):
                    # Cache it
                    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                    with open(cache_path, "w", encoding="utf-8") as f:
                        json.dump(data, f)

            self._parse_modules(data.get("modules", []))
        except CLIError:
            raise
        except Exception as e:
            log_error(f"loading dependency graph: {e}")
            self.graph = {}
            self.reverse_graph = {}
            raise CLIError(f"Unexpected error loading dependency graph: {e}")

    def _parse_modules(self, modules: List[Dict]):
        for mod in modules:
            source = mod.get("source")
            deps = mod.get("dependencies", [])
            self.graph[source] = deps

            for dep in deps:
                resolved = dep.get("resolved")
                if resolved:
                    if resolved not in self.reverse_graph:
                        self.reverse_graph[resolved] = []
                    self.reverse_graph[resolved].append(source)

    def get_dependencies(self, filepath: str) -> List[str]:
        """Returns files that the given file depends on."""
        deps = self.graph.get(filepath, [])
        return [d.get("resolved") for d in deps if d.get("resolved")]

    def get_dependents(self, filepath: str) -> List[str]:
        """Returns files that depend on the given file."""
        return self.reverse_graph.get(filepath, [])

    def find_affected_files(self, changed_files: List[str], depth: int = 2) -> Set[str]:
        """Recursively finds files affected by the changes."""
        affected = set()
        queue = [(f, 0) for f in changed_files]

        while queue:
            file, current_depth = queue.pop(0)
            if file in affected or current_depth > depth:
                continue

            if current_depth > 0:  # Don't add the changed files themselves if we want only 'affected'
                affected.add(file)

            dependents = self.get_dependents(file)
            for dep in dependents:
                queue.append((dep, current_depth + 1))

        return affected

    def get_context_files(self, changed_files: List[str]) -> List[str]:
        """Returns a list of relevant files for context (dependencies + direct dependents)."""
        context = set()
        for f in changed_files:
            # Add direct dependencies
            context.update(self.get_dependencies(f))
            # Add direct dependents
            context.update(self.get_dependents(f))

        # Filter out the changed files themselves and ensure they exist
        result = [f for f in context if f not in changed_files and os.path.exists(os.path.join(self.root_dir, f))]
        return result
