# File Analysis Agent

Utilities for converting a single local document to Markdown and exposing light‑weight
inspection tools for other AI agents.  The project focuses on reusable Markdown
conversion, caching and simple line based queries.

## Installation

```bash
pip install -e .
# optional dependency for formats like PDF, DOCX, PPTX ...
pip install -e .[docling]
```

## Configuration

Default settings live in the ``file_analysis_agent`` section of
``organizer.config.json``:

```json
"file_analysis_agent": {
  "model": "gpt-5-nano",
  "cache_dir": "~/.file_analysis_cache",
  "max_return_chars": 5000,
  "regex_default_flags": "im",
  "token_limit": 4000,
  "encoding_name": "cl100k_base",
  "conversion_timeout": 45
}
```

Edit this file to change the defaults.  Settings can also be tweaked at runtime:

```python
from file_analysis_agent import update_config
update_config(max_return_chars=10000)
```

## Usage

### Tools directly

The tools can be imported and exercised independently of any LLM:

```python
from file_analysis_agent import tools

# convert and cache
tools.set("/path/to/document.pdf")

# inspect
snippet = tools.top(start_line=10, num_lines=5)
print(snippet["text"])
```

Run the tests for individual tools with:

```bash
pytest tests/test_tools.py::test_set_and_top
```

### Pydantic agent

A ready‑made `pydantic_ai.Agent` exposes the same tools for use in larger
workflows:

```python
from file_analysis_agent.agent import agent

agent.run("Use set('/path/to/file.txt')")
agent.run("Show the top 5 lines")
```

## Custom runs and cache management

`cache_dir` controls where converted Markdown and metadata are stored.  Remove a
cached file programmatically with:

```python
from file_analysis_agent import tools

tools.delete_cache("/path/to/file.txt")
```

## Testing

Run the full test suite with:

```bash
pytest
```

## Design notes

* Configuration is validated with Pydantic and stored in a JSON file for easy editing.
* Markdown conversion uses [IBM Docling](https://github.com/docling-project) when available; plain text formats are read directly.
* Results are cached with atomic writes and accompanied by metadata sidecars.
* Tool outputs are truncated to `max_return_chars` and `read_full_file` enforces a
  token limit to keep responses compact.
* Only one document is analysed at a time to keep the interface predictable.
