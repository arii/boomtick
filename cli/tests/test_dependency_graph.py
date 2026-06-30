import json
import os
import pytest
from dev_tools.services.dependency_graph import DependencyGraph

def test_dependency_graph_parsing(tmp_path):
    graph_data = {
        "modules": [
            {
                "source": "src/a.ts",
                "dependencies": [{"resolved": "src/b.ts"}]
            },
            {
                "source": "src/b.ts",
                "dependencies": []
            }
        ]
    }

    # Create a dummy artifact
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    graph_file = artifact_dir / "dependency-graph.json"
    graph_file.write_text(json.dumps(graph_data))

    # Instantiate with tmp_path
    dg = DependencyGraph(root_dir=str(tmp_path))

    assert dg.get_dependencies("src/a.ts") == ["src/b.ts"]
    assert dg.get_dependents("src/b.ts") == ["src/a.ts"]

    # Create the file so it exists
    src_dir = tmp_path / "src"
    src_dir.mkdir(exist_ok=True)
    (src_dir / "b.ts").touch()

    assert dg.get_context_files(["src/a.ts"]) == ["src/b.ts"]
