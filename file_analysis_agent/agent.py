"""PydanticAI agent exposing file analysis tools."""
from __future__ import annotations

from pydantic_ai import Agent

from .agent_tools import tools

# Configure the underlying LLM model. This is a placeholder string and can be
# replaced by any model supported by PydanticAI in real usage.
agent = Agent(
    "google-gla:gemini-1.5-flash",
    system_prompt=(
        "You are a file analysis assistant. Use the provided tools to load files "
        "and inspect their contents."
    ),
)


@agent.tool_plain
def set(path: str, force: bool = False) -> dict:
    """Load a file for analysis, converting and caching markdown as needed."""
    return tools.set(path, force=force)


@agent.tool_plain
def top(start_line: int = 1, num_lines: int = 50) -> dict:
    """Return a slice of lines from the cached markdown starting at ``start_line``."""
    return tools.top(start_line=start_line, num_lines=num_lines)


@agent.tool_plain
def tail(num_lines: int = 50) -> dict:
    """Return the last ``num_lines`` from the cached markdown."""
    return tools.tail(num_lines=num_lines)


@agent.tool_plain
def read_full_file() -> dict:
    """Return the full cached markdown subject to token limits."""
    return tools.read_full_file()


@agent.tool_plain
def find_within_doc(regex_string: str, flags: str | None = None, max_hits: int = 50) -> dict:
    """Find regex matches line by line in the cached markdown."""
    return tools.find_within_doc(regex_string, flags=flags, max_hits=max_hits)


@agent.tool_plain
def get_random_lines(start: int = 1, num_lines: int = 20, seed: int | None = None) -> dict:
    """Return a random contiguous window of lines from the cached markdown."""
    return tools.get_random_lines(start=start, num_lines=num_lines, seed=seed)


@agent.tool_plain
def get_file_metadata() -> dict:
    """Return metadata about the current file and cache entry."""
    return tools.get_file_metadata()
