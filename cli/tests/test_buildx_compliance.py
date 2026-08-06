# pylint: disable=import-outside-toplevel,missing-docstring,protected-access,unused-argument
import os
import importlib.util

# Find path to verify-ci-workflows.py
SCRIPT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../scripts/verify-ci-workflows.py"))

def get_verify_module():
    spec = importlib.util.spec_from_file_location("verify_ci_workflows", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_compliant_with_setup_docker_buildx():
    verify_module = get_verify_module()

    content = """
name: Compliant Workflow
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - name: Set up Docker Buildx
        uses: ./.github/actions/setup-docker-buildx
      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          push: true
          cache-to: type=gha,mode=max
"""
    violations = verify_module.check_workflow_file("compliant.yml", content)
    assert len(violations) == 0

def test_compliant_with_docker_setup_buildx_action():
    verify_module = get_verify_module()

    content = """
name: Compliant Workflow
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          push: true
          cache-to: type=gha,mode=max
"""
    violations = verify_module.check_workflow_file("compliant.yml", content)
    assert len(violations) == 0

def test_non_compliant_missing_setup():
    verify_module = get_verify_module()

    content = """
name: Non-Compliant Workflow
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          push: true
          cache-to: type=gha,mode=max
"""
    violations = verify_module.check_workflow_file("non-compliant.yml", content)
    assert len(violations) == 1
    assert "exports GHA cache" in violations[0]
    assert "not preceded by" in violations[0]

def test_compliant_without_cache_to():
    verify_module = get_verify_module()

    content = """
name: Compliant Workflow Without Cache
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          push: true
"""
    violations = verify_module.check_workflow_file("compliant.yml", content)
    assert len(violations) == 0
