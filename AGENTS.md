# AGENTS

This repository hosts multiple agents for organizing files and related utilities. The instructions in this file apply to the entire repository.

## Repository layout
- `agent_utils/` – Shared utilities such as the vector database helper.
- `file_analysis_agent/` – Tools for converting and analyzing documents.
  - `agent_tools/` – Helper classes for analysis, caching, conversion, and tooling.
- `file_organization_decider_agent/` – Chooses how files should be organized.
  - `agent_tools/` – Decision helpers and supporting utilities.
- `file_organization_planner_agent/` – Plans folder structures and file placement.
  - `agent_tools/` – Planner helpers.
- `foldermate/` – Web interface and static assets.
- `tests/` – Pytest suite verifying the behaviour of the agents.

## Code style
- Conform to **PEP 8** for all Python code.
- Use type hints throughout.
- Write docstrings in **reStructuredText** format.

## Quality requirements
- Run `pylint` on touched packages and strive for a score **> 9.0**.
- Run the full test suite with `pytest` and ensure all tests pass before committing.

## Additional best practices
- Keep functions and modules focused and small.
- Prefer explicit names over abbreviations.
- Update this file when adding new top-level folders or major conventions.
- Do not commit secrets or credentials.
- Use descriptive commit messages summarizing rationale.

