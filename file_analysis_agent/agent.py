"""PydanticAI agent exposing file analysis tools."""
from __future__ import annotations

from pathlib import Path
import json
import logging
from typing import Dict, Any, AsyncIterable

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits
from pydantic_ai.messages import AgentStreamEvent
from pydantic_ai.tools import RunContext

from file_analysis_agent.agent_tools import tools
from agent_utils import setup_logging

PROMPT_PATH = Path(__file__).with_name("prompt.md")
ROOT_CONFIG = Path(__file__).resolve().parents[1] / "organizer.config.json"

setup_logging(str(ROOT_CONFIG))
logger = logging.getLogger(__name__)


def load_config() -> Dict[str, Any]:
    """Load configuration for the agent from the main config file."""
    with ROOT_CONFIG.open(encoding="utf-8") as config_file:
        cfg = json.load(config_file)
    agent_cfg = cfg.get("file_analysis_agent", {})
    agent_cfg.setdefault("api_key", cfg.get("api_key", ""))
    return agent_cfg


def build_agent() -> Agent:
    """Create an :class:`Agent` configured for file analysis."""
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
        logger.info("agent event: %s", event)


@agent.tool_plain
def load_file(path: str) -> dict:
    """Load a file for analysis, converting and caching markdown as needed."""
    return tools.set(path, force=False)


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
def find_within_doc(regex_string: str, max_hits: int = 50) -> dict:
    """Find regex matches line by line in the cached markdown."""
    return tools.find_within_doc(regex_string, max_hits=max_hits)


@agent.tool_plain
def get_random_lines(start: int = 1, num_lines: int = 20) -> dict:
    """Return a random contiguous window of lines from the cached markdown."""
    return tools.get_random_lines(start=start, num_lines=num_lines)


@agent.tool_plain
def get_file_metadata() -> dict:
    """Return metadata about the current file and cache entry."""
    return tools.get_file_metadata()


@agent.tool_plain
def get_text_content_length() -> int:
    """Return the length of text content of the current file."""
    return tools.get_text_content_length()


def ask_file_analysis_agent(
    path: str,
    query: str = "Please prepare the standard report after analyzing file:",
) -> str:
    """Execute a query against the file analysis agent.

    Parameters
    ----------
    path:
        Path to the file to analyse.
    query:
        Prompt requesting the analysis. ``path`` is appended to this string.

    Returns
    -------
    str
        The agent's textual response.
    """
    agent_query = f"{query} {path}"
    logger.info("file_analysis_agent query: %s", agent_query)
    response = agent.run_sync(
        agent_query,
        usage_limits=UsageLimits(request_limit=20),
        event_stream_handler=_log_event_stream,
    )
    logger.info("file_analysis_agent response: %s", response.output)
    return response.output


__all__ = ["ask_file_analysis_agent", "agent"]
