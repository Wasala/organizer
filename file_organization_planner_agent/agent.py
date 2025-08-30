"""PydanticAI agent exposing file organization planner tools."""
from __future__ import annotations

from pydantic_ai import Agent

from .agent_tools import tools

agent = Agent(
    "google-gla:gemini-1.5-flash",
    system_prompt=(
        "You are a file organization planning assistant. Use tools to search file reports,"
        " manage notes, and inspect folder structures."
    ),
)


@agent.tool_plain
def find_similar_file_reports(path: str, top_k: int = 10) -> dict:
    """Find semantically similar file reports for ``path``."""
    return tools.find_similar_file_reports(path, top_k=top_k)


@agent.tool_plain
def append_organization_notes(ids: list[int], notes: str) -> dict:
    """Append organization notes to the given file ``ids``."""
    return tools.append_organization_notes(ids, notes)


@agent.tool_plain
def get_file_report(path: str) -> dict:
    """Retrieve the stored file report for ``path``."""
    return tools.get_file_report(path)


@agent.tool_plain
def get_folder_instructions() -> dict:
    """Return user folder organization instructions."""
    return tools.get_folder_instructions()


@agent.tool_plain
def target_folder_tree(path: str) -> str:
    """Return a folder tree for ``path`` with a heading."""
    return tools.target_folder_tree(path)
