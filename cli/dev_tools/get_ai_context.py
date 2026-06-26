import os
import sys
import json

# Add dev-tools to path
sys.path.append(os.path.join(os.getcwd(), "dev-tools"))

from tdw_services.services.dependency_graph import DependencyGraph
from tdw_services.services.vector_store import VectorStore

def get_context(filepath: str, diff_text: str, graph: DependencyGraph, store: VectorStore, n_results: int = 3):
    context = {
        "path": filepath,
        "dependencies": [],
        "dependents": [],
        "semantic": []
    }

    if not isinstance(filepath, str) or not isinstance(diff_text, str) or not filepath.strip() or not diff_text.strip():
        return context

    context["dependencies"] = graph.get_dependencies(filepath)
    context["dependents"] = graph.get_dependents(filepath)

    try:
        # Use diff_text for semantic search
        results = store.query(diff_text, n_results=n_results)
        for res in results:
            if res['metadata'].get('path') != filepath:
                context["semantic"].append({
                    "path": res['metadata'].get('path'),
                    "document": res['document']
                })
    except Exception as e:
        print(f"Error querying vector store: {e}", file=sys.stderr)

    return context

if __name__ == "__main__":
    # Load input from stdin to avoid E2BIG
    try:
        input_data = json.load(sys.stdin)
    except Exception as e:
        print(f"Error parsing input JSON: {e}", file=sys.stderr)
        sys.exit(1)

    files_data = input_data.get("files", [])
    if not files_data:
        print(json.dumps([]))
        sys.exit(0)

    # Initialize services once
    graph = DependencyGraph()
    store = VectorStore()

    results = []
    for item in files_data:
        filepath = item.get("path")
        diff_text = item.get("diff")
        if filepath and diff_text:
            results.append(get_context(filepath, diff_text, graph, store))

    print(json.dumps(results))
