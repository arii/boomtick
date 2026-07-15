# Problem Statement
Consumers integrating Boomtick currently require complex submodule checkouts to utilize the CLI component. This creates friction and fragile dependencies on the repository's internal structure.

# Goal
Implement PyPI packaging for the Boomtick CLI to enable seamless, submodule-free integration for downstream consumers via standard Python package management (`pip install`).

# Non-Goals
- We will not address Docker container packaging in this issue.
- We will not refactor the CLI's internal logic, only how it is distributed.

# Proposed Approach
1. Ensure the `cli/` directory is properly structured for PyPI distribution (e.g., `pyproject.toml` or `setup.py` metadata is complete).
2. Integrate the build and publish steps into the automated release workflow (`release-logic.yml`).
3. Authenticate securely with PyPI to publish the package.

# Alternatives Considered
- Continuing to recommend Git submodules: Rejected because it creates a poor developer experience and complicates version management for consumers.

# Architectural Impact
Shifts the consumption model from Git-based inclusion to artifact-based dependency management. This significantly simplifies onboarding and decouples consumer repositories from Boomtick's repository structure.

# Scope
Limited to the configuration of the Python package metadata and the CI pipeline steps required to publish the CLI artifact to PyPI.

# SPECIFY SCOPE
Limited to the configuration of the Python package metadata and the CI pipeline steps required to publish the CLI artifact to PyPI.

# DEFINITION OF DONE
- The Python CLI can be successfully built into a distribution package (`sdist`/`wheel`).
- The release pipeline successfully authenticates and publishes the package to PyPI on tagged releases.

# UNDERSTAND THE ISSUE
- Verify the current build capabilities of the `cli` component.
- Review `release-logic.yml` to determine where PyPI publication steps should be added.

# DETERMINE APPROACH
- Configure the workflow to build the Python package.
- Add the necessary action steps (e.g., `pypa/gh-action-pypi-publish`) to push the artifact securely to PyPI.