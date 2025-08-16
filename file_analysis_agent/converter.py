"""File conversion utilities using Docling where necessary."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from .config import CONFIG

logger = logging.getLogger(__name__)

# Extensions treated as plain text
TEXT_EXTENSIONS = {
    ".txt", ".md", ".rst", ".json", ".csv", ".yaml", ".yml", ".ini", ".toml"
}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def convert_to_markdown(path: Path) -> str:
    """Convert a file to markdown using Docling when required."""
    ext = path.suffix.lower()
    if ext in TEXT_EXTENSIONS:
        return _read_text(path)

    try:
        from docling.document_converter import DocumentConverter
    except Exception as exc:  # pragma: no cover - depends on optional docling
        raise RuntimeError(
            "Docling is required to convert this file. Install 'docling'."
        ) from exc

    converter = DocumentConverter()
    result = converter.convert(str(path))
    # Docling's result object exposes markdown via `.document.export_to_markdown()`
    try:
        md = result.document.export_to_markdown()
    except AttributeError:
        # Fallback for older versions
        md = result.markdown
    return md
