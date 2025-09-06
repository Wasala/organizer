"""Shared utilities for the organizer agents.

This module also configures logging for the project. Logs are written to a
timestamped file located in the directory specified by ``log_dir`` in the
main ``organizer.config.json`` file. If the configuration file is missing the
``log_dir`` entry, logs default to the current working directory. The default
configuration file path is resolved relative to the repository root so that
logging behaves consistently regardless of the current working directory.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Union


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "organizer.config.json"


def setup_logging(config_path: Union[str, Path] = DEFAULT_CONFIG_PATH) -> Path:
    """Configure root logging from the organizer configuration.

    Parameters
    ----------
    config_path:
        Path to the JSON configuration file. Defaults to the repository's
        ``organizer.config.json``.

    Returns
    -------
    Path
        The path to the log file being used.
    """

    config_path = Path(config_path)
    try:
        with config_path.open("r", encoding="utf-8") as fh:
            cfg = json.load(fh)
    except FileNotFoundError:  # pragma: no cover - handled gracefully
        cfg = {}

    log_dir = Path(cfg.get("log_dir", "."))
    if not log_dir.is_absolute():
        log_dir = config_path.parent / log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"{timestamp}.log"

    logging.basicConfig(
        filename=str(log_file),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
        force=True,
    )
    return log_file


# Configure logging immediately when this package is imported.
setup_logging()
