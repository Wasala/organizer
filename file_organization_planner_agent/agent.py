"""PydanticAI agent exposing file organization planner tools."""
from __future__ import annotations

from pathlib import Path
import json

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from .agent_tools import tools

ROOT_CONFIG = Path(__file__).resolve().parents[1] / "organizer.config.json"


def load_config() -> dict:
    """Load configuration for the planner agent from the main config file."""
    with ROOT_CONFIG.open(encoding="utf-8") as config_file:
        cfg = json.load(config_file)
    agent_cfg = cfg.get("file_organization_planner_agent", {})
    agent_cfg.setdefault("api_key", cfg.get("api_key", ""))
    return agent_cfg


_CFG = load_config()
_MODEL = OpenAIModel(
    _CFG.get("model", "gpt-5-nano"),
    provider=OpenAIProvider(api_key=_CFG.get("api_key")),
)

agent = Agent(
    model=_MODEL,
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
