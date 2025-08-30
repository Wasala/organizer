"""PydanticAI agent exposing file organization decider tools."""
from __future__ import annotations

from pydantic_ai import Agent

from .agent_tools import tools

agent = Agent(
    "google-gla:gemini-1.5-flash",
    system_prompt=(
        "You are a file organization decision assistant. Use tools to manage notes "
        "and set planned destinations."
    ),
)


@agent.tool_plain
def append_organization_notes(ids: list[int], notes: str) -> dict:
    """Append organization notes to the given file ``ids``."""
    return tools.append_organization_notes(ids, notes)


@agent.tool_plain
def get_file_report(path: str) -> dict:
    """Retrieve the stored file report for ``path``."""
    return tools.get_file_report(path)


@agent.tool_plain
def set_planned_destination(path: str, planned_dest: str) -> dict:
    """Set the planned destination for ``path``."""
    return tools.set_planned_destination(path, planned_dest)


@agent.tool_plain
def get_organization_notes(path: str) -> dict:
    """Retrieve organization notes for ``path``."""
    return tools.get_organization_notes(path)


@agent.tool_plain
def get_folder_instructions() -> dict:
    """Return user folder organization instructions."""
    return tools.get_folder_instructions()


@agent.tool_plain
def target_folder_tree(path: str) -> str:
    """Return a folder tree for ``path`` with a heading."""
    return tools.target_folder_tree(path)
