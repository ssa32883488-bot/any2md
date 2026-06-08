"""Model storage paths — never on C: drive; portable app uses ANY2MD_APP_ROOT."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _default_models_home() -> Path:
    app = os.environ.get("ANY2MD_APP_ROOT")
    if app:
        return Path(app) / "models"
    return Path(__file__).resolve().parents[1] / "models"


def forbid_c_drive(path: Path) -> None:
    if path.drive.upper() == "C:":
        raise RuntimeError(
            f"模型目录不能设在 C 盘：{path}\n"
            "请选择 exe 所在盘下的 models 目录。"
        )


def resolve_models_home(custom: str | None = None) -> Path:
    """PaddleX cache root; official weights live in ``<home>/official_models``."""
    raw = (
        custom
        or os.environ.get("ANY2MD_MODELS_DIR")
        or os.environ.get("PADDLE_PDX_CACHE_HOME")
        or str(_default_models_home())
    )
    home = Path(raw).expanduser().resolve()
    forbid_c_drive(home)
    home.mkdir(parents=True, exist_ok=True)
    return home


def official_models_dir(home: Path | None = None) -> Path:
    root = home or resolve_models_home()
    return root / "official_models"


def apply_models_home(home: Path) -> Path:
    """Set PaddleX cache env before any paddlex/paddleocr import."""
    forbid_c_drive(home)
    home.mkdir(parents=True, exist_ok=True)
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(home)
    os.environ["ANY2MD_MODELS_DIR"] = str(home)
    return home


def early_models_dir_from_argv(argv: list[str] | None = None) -> str | None:
    args = argv if argv is not None else sys.argv
    for i, arg in enumerate(args):
        if arg in ("--models-dir", "-m") and i + 1 < len(args):
            return args[i + 1]
    return None
