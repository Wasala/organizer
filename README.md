# File Analysis Agent

Utilities for converting a single local document to Markdown and exposing
light‑weight inspection tools for other AI agents. The project focuses on
reusable Markdown conversion, caching and simple line based queries.

## Features

* One time conversion of supported documents to Markdown using [IBM Docling](https://github.com/docling-project).
* Cache management with atomic writes and metadata sidecars.
* PydanticAI compatible tools:
  * `set(path, force=False)` – load and cache a file.
  * `top(start_line=1, num_lines=50)` – return a slice of lines.
  * `tail(num_lines=50)` – return the last lines.
  * `read_full_file()` – return complete Markdown if under token limit.
  * `find_within_doc(regex_string, flags=None, max_hits=50)` – regex search.
  * `get_random_lines(start=1, num_lines=20, seed=None)` – deterministic random window.
  * `get_file_metadata()` – filesystem and cache metadata.
  * `delete_cache(path)` – remove cached entry for a file.

Plain text files (`.txt`, `.md`, `.json`, `.csv`, etc.) are read directly. Other
formats (`.docx`, `.pptx`, `.xlsx`, `.pdf`, …) require the `docling` package.

## Configuration

Configuration lives in `file_analysis_agent.config.AgentConfig`. Values can be
updated at runtime via `file_analysis_agent.config.update_config`.

| Option | Description | Default |
|--------|-------------|---------|
| `cache_dir` | Directory for cached markdown | `~/.file_analysis_cache` |
| `max_return_chars` | Max characters returned by any tool | `5000` |
| `regex_default_flags` | Flags applied when none supplied | `"im"` |
| `token_limit` | Max tokens for `read_full_file` | `4000` |
| `conversion_timeout` | Seconds allowed for conversion/caching | `45` |

## Examples

```python
from file_analysis_agent.agent_tools import tools

# Convert and cache
tools.set("/path/to/document.pdf")

# Inspect
snippet = tools.top(start_line=10, num_lines=5)
print(snippet["text"])
```

## Tests

Run the test suite with:

```bash
pytest
```

## Limitations

* Only one file can be analysed at a time.
* Non text formats require the optional `docling` dependency which is large and
not installed by default.
* No network access or remote file retrieval.
* Outputs are truncated to `max_return_chars`.
