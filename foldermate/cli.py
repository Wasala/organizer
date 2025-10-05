"""Command-line entrypoint for running the FolderMate server."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict

import uvicorn  # pylint: disable=import-error

LOGGER = logging.getLogger(__name__)
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_CONFIG_NAME = "organizer.config.json"


def load_config(config_path: Path) -> Dict[str, Any]:
    """Load and validate the runtime configuration.

    Parameters
    ----------
    config_path:
        Location of the configuration JSON file.

    Returns
    -------
    Dict[str, Any]
        Parsed configuration contents.

    Raises
    ------
    SystemExit
        Raised when the configuration cannot be read or contains invalid JSON.
    """

    try:
        with config_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:  # pragma: no cover - defensive guard
        raise SystemExit(f"Configuration file not found: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in configuration file: {config_path}") from exc


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the CLI entrypoint."""

    parser = argparse.ArgumentParser(description="Run the FolderMate web application.")
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="Hostname or IP address to bind to.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="TCP port number to listen on.",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_NAME,
        help="Path to organizer.config.json.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Parse arguments, load configuration, and start Uvicorn."""

    parser = build_parser()
    args = parser.parse_args(argv)

    config_path = Path(args.config).expanduser().resolve()
    config = load_config(config_path)
    base_dir = config.get("base_dir")
    if base_dir:
        LOGGER.info("Loaded configuration from %s (base_dir=%s)", config_path, base_dir)
    else:
        LOGGER.info("Loaded configuration from %s", config_path)

    uvicorn.run("foldermate.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
