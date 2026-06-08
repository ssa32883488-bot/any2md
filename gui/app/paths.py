"""Resolve application paths — frozen exe is fully self-contained."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def engine_dir() -> Path:
    root = app_root()
    candidates: list[Path] = []
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "engine")
        candidates.extend([root / "_internal" / "engine", root / "engine"])
    else:
        candidates.extend([
            root / "_bundle" / "engine",
            root / "engine",
            root.parent / "any2md" / "engine",  # dev only
        ])
    for p in candidates:
        if p.is_dir():
            return p.resolve()
    raise FileNotFoundError(f"engine 目录未找到：{candidates}")


def default_models_dir() -> Path:
    return app_root() / "models"


def default_output_dir() -> Path:
    return app_root() / "output"


def config_path() -> Path:
    return app_root() / "config.json"


def isolated_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Subprocess env: no PYTHONPATH leakage, anchor to app_root."""
    root = app_root()
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    env.update(
        {
            "ANY2MD_APP_ROOT": str(root),
            "ANY2MD_MODELS_DIR": str(default_models_dir()),
            "PADDLE_PDX_MODEL_SOURCE": "bos",
            "PADDLE_PDX_HUGGING_FACE_ENDPOINT": "https://hf-mirror.com",
            "HF_ENDPOINT": "https://hf-mirror.com",
            "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK": "True",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        }
    )
    if os.name == "nt":
        env["PATH"] = _win_dll_path_prefix() + os.pathsep + env.get("PATH", "")
    if extra:
        env.update(extra)
    return env


def _win_dll_path_prefix() -> str:
    """Prepend torch/paddle DLL dirs so OCR works under CREATE_NO_WINDOW subprocess."""
    import sys

    parts: list[str] = []
    for entry in sys.path:
        sp = Path(entry)
        if not sp.is_dir():
            continue
        for rel in ("torch/lib", "paddle/libs", "cv2"):
            d = sp / rel
            if d.is_dir():
                parts.append(str(d.resolve()))
        for sub in sp.glob("nvidia/*/bin"):
            parts.append(str(sub.resolve()))
        if parts:
            break
    return os.pathsep.join(parts)


def _no_window() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _is_stub_python(path: Path) -> bool:
    s = str(path).replace("/", "\\").lower()
    return "windowsapps" in s or s.endswith("\\python.exe") and "microsoft" in s


def _python_works(path: Path) -> bool:
    if not path.is_file() or _is_stub_python(path):
        return False
    try:
        r = subprocess.run(
            [str(path), "-c", "import sys; print(sys.executable)"],
            capture_output=True,
            timeout=20,
            creationflags=_no_window(),
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        return False


def _discover_pythons() -> list[Path]:
    import shutil

    seen: set[str] = set()
    out: list[Path] = []

    def add(p: Path | str | None) -> None:
        if not p:
            return
        path = Path(p).expanduser()
        key = str(path).lower()
        if key in seen:
            return
        seen.add(key)
        out.append(path)

    root = app_root()
    add(root / "runtime" / "python.exe")
    add(root / "python" / "python.exe")

    try:
        from app.config import get_python_path

        saved = get_python_path()
        if saved:
            add(saved)
    except Exception:
        pass

    custom = os.environ.get("ANY2MD_PYTHON", "").strip()
    if custom:
        add(custom)

    # Common install locations (before PATH stub / unrelated versions)
    for base in (Path("F:/Python"), Path("D:/Python"), Path("C:/Python")):
        if base.is_dir():
            for exe in sorted(base.rglob("python.exe")):
                if exe.parent.name.lower() not in ("scripts", "venv", ".venv"):
                    add(exe)

    if not is_frozen():
        add(Path(r"F:\Python\Python 3.13.0\python.exe"))

    search_roots = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python",
        Path(os.environ.get("ProgramFiles", "")) / "Python",
    ]
    for base in search_roots:
        if not base.is_dir():
            continue
        for exe in sorted(base.rglob("python.exe")):
            add(exe)

    for name in ("python", "python3"):
        found = shutil.which(name)
        add(found)

    return out


def validate_python(path: Path) -> bool:
    return _python_works(path)


def _paddle_pkg_dir(python: Path) -> Path | None:
    """Fast check: paddle package exists beside this python.exe (no import)."""
    root = python.resolve().parent
    for rel in (
        ("Lib", "site-packages", "paddle"),
        ("lib", "site-packages", "paddle"),
    ):
        pkg = root.joinpath(*rel)
        if (pkg / "__init__.py").is_file():
            return pkg
    # venv: Scripts/python.exe -> Lib/site-packages
    if root.name.lower() == "scripts":
        pkg = root.parent / "Lib" / "site-packages" / "paddle"
        if (pkg / "__init__.py").is_file():
            return pkg
    return None


def _has_paddle(path: Path) -> bool:
    if _paddle_pkg_dir(path):
        return True
    try:
        r = subprocess.run(
            [str(path), "-c", "import paddle; print('OK')"],
            capture_output=True,
            text=True,
            timeout=90,
            creationflags=_no_window(),
        )
        return "OK" in (r.stdout or "")
    except (OSError, subprocess.TimeoutExpired):
        return False


def find_python(*, require_paddle: bool = False) -> Path | None:
    """Portable runtime first; skip Windows Store stub; prefer Paddle-capable Python."""
    try:
        from app.config import get_python_path

        saved = get_python_path()
        if saved and _python_works(saved):
            if not require_paddle or _has_paddle(saved):
                return saved.resolve()
    except Exception:
        pass

    for cand in _discover_pythons():
        if not _python_works(cand):
            continue
        if require_paddle and not _has_paddle(cand):
            continue
        return cand.resolve()

    return None


def python_not_found_message() -> str:
    root = app_root()
    return (
        "未找到可用的 Python 运行时（paddlepaddle-gpu 环境）。\n\n"
        f"请将含 Paddle 的 python.exe 放到：\n  {root / 'runtime' / 'python.exe'}\n\n"
        "或在菜单「设置 → 选择 Python 解释器…」手动指定，\n"
        "也可设置环境变量 ANY2MD_PYTHON。"
    )
