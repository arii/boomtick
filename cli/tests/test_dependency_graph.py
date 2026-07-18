# pylint: disable=missing-docstring,too-many-branches,too-many-nested-blocks,line-too-long
import json

from dev_tools.services.dependency_graph import DependencyGraph, validate_and_sanitize_graph_data


def test_dependency_graph_parsing(tmp_path):
    graph_data = {
        "modules": [
            {"source": "src/a.ts", "dependencies": [{"resolved": "src/b.ts"}]},
            {"source": "src/b.ts", "dependencies": []},
        ]
    }
    validated_data = validate_and_sanitize_graph_data(graph_data)

    # Create a dummy artifact
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    graph_file = artifact_dir / "dependency-graph.json"
    graph_file.write_text(json.dumps(validated_data))

    # Instantiate with tmp_path
    dg = DependencyGraph(root_dir=str(tmp_path))

    assert dg.get_dependencies("src/a.ts") == ["src/b.ts"]
    assert dg.get_dependents("src/b.ts") == ["src/a.ts"]

    # Create the file so it exists
    src_dir = tmp_path / "src"
    src_dir.mkdir(exist_ok=True)
    (src_dir / "b.ts").touch()

    assert dg.get_context_files(["src/a.ts"]) == ["src/b.ts"]


def test_find_affected_files_complex(tmp_path):
    # D depends on C and B, C depends on A, B depends on A
    # Wait, reverse graph: dependents of A are B and C, dependents of B is D, dependents of C is D
    # A is changed. Dependents of A: B, C.
    # Dependents of B: D. Dependents of C: D.
    # Multiple paths to D: A -> B -> D, and A -> C -> D.
    graph_data = {
        "modules": [
            {"source": "src/d.ts", "dependencies": [{"resolved": "src/b.ts"}, {"resolved": "src/c.ts"}]},
            {"source": "src/b.ts", "dependencies": [{"resolved": "src/a.ts"}]},
            {"source": "src/c.ts", "dependencies": [{"resolved": "src/a.ts"}]},
            {"source": "src/a.ts", "dependencies": []},
        ]
    }
    validated_data = validate_and_sanitize_graph_data(graph_data)

    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    graph_file = artifact_dir / "dependency-graph.json"
    graph_file.write_text(json.dumps(validated_data))

    dg = DependencyGraph(root_dir=str(tmp_path))

    # A changed, depth=2.
    # Level 1: B, C (depth 1)
    # Level 2: D, D (depth 2) -> if we did not have visited/affected check before push, D would be added twice!
    affected = dg.find_affected_files(["src/a.ts"], depth=2)
    assert affected == {"src/b.ts", "src/c.ts", "src/d.ts"}

    # With depth=1, only B and C should be affected
    affected_depth_1 = dg.find_affected_files(["src/a.ts"], depth=1)
    assert affected_depth_1 == {"src/b.ts", "src/c.ts"}


def test_find_affected_files_cycle(tmp_path):
    # Cyclic dependencies: A depends on B, B depends on A (so dependents are mutual)
    graph_data = {
        "modules": [
            {"source": "src/a.ts", "dependencies": [{"resolved": "src/b.ts"}]},
            {"source": "src/b.ts", "dependencies": [{"resolved": "src/a.ts"}]},
        ]
    }
    validated_data = validate_and_sanitize_graph_data(graph_data)

    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    graph_file = artifact_dir / "dependency-graph.json"
    graph_file.write_text(json.dumps(validated_data))

    dg = DependencyGraph(root_dir=str(tmp_path))

    affected = dg.find_affected_files(["src/a.ts"], depth=2)
    # Changed file itself is excluded from affected since current_depth > 0.
    # Dependents of A: B. Dependents of B: A (but A was in changed_files, hence visited initially, so it won't be traversed again).
    assert affected == {"src/b.ts"}
