"""Shared utilities for the organizer agents.

This module also configures logging for the project.  Logs are written to a
timestamped file located in the directory specified by ``log_dir`` in the main
``organizer.config.json`` file.  If the configuration file is missing the
``log_dir`` entry, logs default to the current working directory.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path


def setup_logging(config_path: str = "organizer.config.json") -> Path:
    """Configure root logging from the organizer configuration.

    Parameters
    ----------
    config_path:
        Path to the JSON configuration file.

    Returns
    -------
    Path
        The path to the log file being used.
    """

    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
    except FileNotFoundError:  # pragma: no cover - handled gracefully
        cfg = {}

    log_dir = Path(cfg.get("log_dir", "."))
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"{timestamp}.log"

    logging.basicConfig(
        filename=str(log_file),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    return log_file


# Configure logging immediately when this package is imported.
setup_logging()
