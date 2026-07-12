# pylint: disable=missing-docstring,no-value-for-parameter
import json
import sys

import click
from dev_tools.services.dependency_graph import DependencyGraph
from dev_tools.services.vector_store import VectorStore


def get_context(filepath: str, diff_text: str, graph: DependencyGraph, store: VectorStore, n_results: int = 3):
    context = {"path": filepath, "dependencies": [], "dependents": [], "semantic": []}

    if not isinstance(filepath, str) or not isinstance(diff_text, str) or not filepath.strip() or not diff_text.strip():
        return context

    context["dependencies"] = graph.get_dependencies(filepath)
    context["dependents"] = graph.get_dependents(filepath)

    try:
        # Use diff_text for semantic search
        results = store.query(diff_text, n_results=n_results)
        for res in results:
            if res["metadata"].get("path") != filepath:
                context["semantic"].append({"path": res["metadata"].get("path"), "document": res["document"]})
    except Exception as e:
        print(f"Error querying vector store: {e}", file=sys.stderr)

    return context


@click.command()
@click.argument("input_file", type=click.File("r"), default="-")
def main(input_file):
    """Retrieve dependency and semantic context for a set of changed files."""
    try:
        input_data = json.load(input_file)
    except Exception as e:
        click.echo(f"Error parsing input JSON: {e}", err=True)
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

    click.echo(json.dumps(results))


if __name__ == "__main__":
    main()
