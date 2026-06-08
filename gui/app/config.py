"""Persist wizard / app settings — all paths stay under app_root (isolated portable app)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.paths import app_root, config_path, default_models_dir, default_output_dir

# Re-export chunk helpers for callers that import from config
from app.chunk_catalog import chunk_model_ready, chunk_model_status  # noqa: F401

_REQUIRED_MODELS = ("PP-DocLayoutV3", "PaddleOCR-VL-1.6")


def load_config() -> dict[str, Any]:
    path = config_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(data: dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _under_app_root(path: Path) -> Path:
    """Keep data directories inside the portable app folder only."""
    root = app_root().resolve()
    path = path.expanduser().resolve()
    try:
        path.relative_to(root)
        return path
    except ValueError:
        return path  # caller decides fallback


def get_models_dir() -> Path:
    """Models always live in <exe>/models unless already configured under app_root."""
    default = default_models_dir().resolve()
    raw = load_config().get("models_dir")
    if not raw:
        return default
    path = Path(raw).expanduser().resolve()
    root = app_root().resolve()
    try:
        path.relative_to(root)
        return path
    except ValueError:
        return default


def get_output_dir() -> Path:
    default = default_output_dir().resolve()
    raw = load_config().get("output_dir")
    if not raw:
        return default
    path = Path(raw).expanduser().resolve()
    root = app_root().resolve()
    try:
        path.relative_to(root)
        return path
    except ValueError:
        return default


def models_ready(home: Path | None = None) -> tuple[bool, str]:
    root = home or get_models_dir()
    official = root / "official_models"
    if not official.is_dir():
        return False, f"模型目录不存在：{official}\n请在「设置 → 重新运行首次设置」中下载模型。"
    missing = []
    for name in _REQUIRED_MODELS:
        d = official / name
        if not d.is_dir():
            missing.append(name)
            continue
        has_w = any(d.glob("*.pdiparams")) or any(d.glob("*.safetensors"))
        if not has_w:
            missing.append(name)
    if missing:
        return False, (
            f"缺少模型：{', '.join(missing)}\n"
            f"目录：{official}\n"
            "请重新运行首次设置并完成下载（约 2 GB，国内镜像）。"
        )
    return True, str(official)


def get_python_path() -> Path | None:
    raw = load_config().get("python_path")
    if raw:
        p = Path(raw).expanduser()
        if p.is_file():
            return p.resolve()
    return None


def set_python_path(path: Path) -> None:
    save_config({**load_config(), "python_path": str(path.resolve())})


def ensure_portable_config() -> None:
    """Normalize config to portable layout under app_root."""
    cfg = load_config()
    cfg["models_dir"] = str(get_models_dir())
    cfg["output_dir"] = str(get_output_dir())
    save_config(cfg)
