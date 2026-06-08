"""Batch output folder helper for GUI (mirrors engine/output_layout.py)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

_SUBDIRS = ("md", "json", "chunks", "assets")


def create_batch_dir(base: Path) -> Path:
    base = base.expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    root = base / ts
    for name in _SUBDIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def is_batch_root(path: Path) -> bool:
    path = path.expanduser().resolve()
    return path.is_dir() and (path / "md").is_dir() and (path / "json").is_dir()
