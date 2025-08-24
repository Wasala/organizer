"""PydanticAI agent exposing file analysis tools."""
from __future__ import annotations
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

from file_analysis_agent.agent_tools import tools

system_prompt = Path("./prompt.md").read_text(encoding="utf-8")
key = "we need to get tis from config.json"

model = OpenAIModel('gpt-5-nano', provider=OpenAIProvider(api_key=key))

# Configure the underlying LLM model. This is a placeholder string and can be
# replaced by any model supported by PydanticAI in real usage.
agent = Agent(
    model=model,
    system_prompt=system_prompt,
    retries=2,

    )



@agent.tool_plain
def set(path: str) -> dict:
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
    """Find regex matches line by line in the cached markdown. Current regex flags: im"""
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
def get_text_content_length() -> dict:
    """Return no of lines textual content in the file."""
    return tools.get_file_metadata()

def ask_file_analysis_agent(path, query="Please prepare the standard report after analyzing file:"):
    agent_query = query + path
    response = agent.run_sync(agent_query, usage_limits=UsageLimits(request_limit=20))
    return response.output

agent_output = ask_file_analysis_agent(path= "d:/laya-claim-6830304-2024-01-25.pdf")
print(agent_output)