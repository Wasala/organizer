"""PydanticAI agent exposing file organization planner tools."""
from __future__ import annotations

from pathlib import Path
import json
import logging
from typing import Any, AsyncIterable, Dict

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits
from pydantic_ai.messages import AgentStreamEvent
from pydantic_ai.tools import RunContext

from .agent_tools import tools
from agent_utils import setup_logging


PROMPT_PATH = Path(__file__).with_name("prompt.md")
ROOT_CONFIG = Path(__file__).resolve().parents[1] / "organizer.config.json"

setup_logging(str(ROOT_CONFIG))
logger = logging.getLogger(__name__)


def load_config() -> Dict[str, Any]:
    """Load configuration for the planner agent from the main config file."""
    with ROOT_CONFIG.open(encoding="utf-8") as config_file:
        cfg = json.load(config_file)
    agent_cfg = cfg.get("file_organization_planner_agent", {})
    agent_cfg.setdefault("api_key", cfg.get("api_key", ""))
    return agent_cfg


def build_agent() -> Agent:
    """Create an :class:`Agent` configured for planning organization."""
    config = load_config()
    api_key = config.get("api_key")
    model_name = config.get("model", "gpt-5-nano")
    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    model = OpenAIModel(model_name, provider=OpenAIProvider(api_key=api_key))
    return Agent(model=model, system_prompt=system_prompt, retries=2)


agent = build_agent()


async def _log_event_stream(
    _: RunContext[Any], stream: AsyncIterable[AgentStreamEvent]
) -> None:
    """Log events emitted during agent execution."""
    async for event in stream:
        logger.info("planner agent event: %s", event)


@agent.tool_plain
def find_similar_file_reports(path: str) -> dict:
    """Find semantically similar file reports for ``path``."""
    return tools.find_similar_file_reports(path, top_k=10)


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
def target_folder_tree() -> dict:
    """Return a folder tree for the configured target directory."""
    return tools.target_folder_tree()


def ask_file_organization_planner_agent(
    path: str,
    query: str = "Please plan the organization for file:",
) -> str:
    """Execute a query against the file organization planner agent.

    Parameters
    ----------
    path:
        Path to the file for which planning is requested.
    query:
        Prompt requesting the plan. ``path`` is appended to this string.

    Returns
    -------
    str
        The agent's textual response.
    """

    agent_query = f"{query} {path}"
    logger.info("file_organization_planner_agent query: %s", agent_query)
    response = agent.run_sync(
        agent_query,
        usage_limits=UsageLimits(request_limit=20),
        event_stream_handler=_log_event_stream,
    )
    logger.info(
        "file_organization_planner_agent response: %s", response.output
    )
    print(response)
    return response.output


__all__ = ["ask_file_organization_planner_agent", "agent"]
