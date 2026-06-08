"""Apply PaddleX / PaddleOCR runtime defaults."""

from __future__ import annotations

import os
from pathlib import Path

from model_paths import apply_models_home, resolve_models_home

# Domestic mirrors (override via env if needed).
_DEFAULT_MODEL_SOURCE = "bos"  # paddle-model-ecology.bj.bcebos.com
_DEFAULT_HF_ENDPOINT = "https://hf-mirror.com"


def apply_cn_mirrors() -> None:
    """Prefer domestic CDNs for PaddleX models; HF fallback via hf-mirror."""
    os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", _DEFAULT_MODEL_SOURCE)
    os.environ.setdefault("PADDLE_PDX_HUGGING_FACE_ENDPOINT", _DEFAULT_HF_ENDPOINT)
    os.environ.setdefault("HF_ENDPOINT", _DEFAULT_HF_ENDPOINT)


def mirror_summary() -> dict[str, str]:
    return {
        "model_source": os.environ.get("PADDLE_PDX_MODEL_SOURCE", _DEFAULT_MODEL_SOURCE),
        "hf_endpoint": os.environ.get("PADDLE_PDX_HUGGING_FACE_ENDPOINT", _DEFAULT_HF_ENDPOINT),
    }


def apply_engine_env(models_home: Path | str | None = None) -> Path:
    apply_cn_mirrors()
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    os.environ.setdefault("GLOG_minloglevel", "2")
    _prepend_win_dll_dirs()
    home = resolve_models_home(str(models_home) if models_home else None)
    return apply_models_home(home)


def _prepend_win_dll_dirs() -> None:
    """Ensure torch/paddle native DLLs resolve in GUI subprocesses (minimal PATH)."""
    if os.name != "nt":
        return
    import sys

    site_packages: list[Path] = []
    for entry in sys.path:
        p = Path(entry)
        if p.is_dir() and (p / "torch").is_dir():
            site_packages.append(p)
            break
    if not site_packages:
        return

    sp = site_packages[0]
    dll_dirs = [
        sp / "torch" / "lib",
        sp / "paddle" / "libs",
        sp / "cv2",
    ]
    for sub in sp.glob("nvidia/*/bin"):
        dll_dirs.append(sub)
    for sub in sp.glob("nvidia/*/lib"):
        dll_dirs.append(sub)

    prepend: list[str] = []
    for d in dll_dirs:
        if not d.is_dir():
            continue
        s = str(d.resolve())
        prepend.append(s)
        add = getattr(os, "add_dll_directory", None)
        if add:
            try:
                add(s)
            except OSError:
                pass
    if prepend:
        os.environ["PATH"] = os.pathsep.join(prepend) + os.pathsep + os.environ.get("PATH", "")
    _preload_torch_on_windows()


def _preload_torch_on_windows() -> None:
    """Import torch before paddle; otherwise paddle breaks torch DLL loading on Windows."""
    import sys

    if os.name != "nt":
        return
    if "torch" in sys.modules:
        return
    try:
        import torch  # noqa: F401
    except Exception:
        pass
