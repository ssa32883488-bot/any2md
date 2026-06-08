"""Built-in BOS model download (stdlib only — works inside frozen exe)."""

from __future__ import annotations

import shutil
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

BOS_BASE = (
    "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0"
)

CATALOG: dict[str, dict] = {
    "PP-DocLayoutV3": {
        "name": "PP-DocLayoutV3",
        "label": "版面分析模型",
        "tar": "PP-DocLayoutV3_infer.tar",
    },
    "PaddleOCR-VL-1.6": {
        "name": "PaddleOCR-VL-1.6",
        "label": "文档语义 / VLM 模型",
        "tar": "PaddleOCR-VL-1.6_infer.tar",
    },
}

ProgressFn = Callable[[str, str, float | None], None]

# BOS 对单连接限速明显；多模型并行可叠带宽（实测约 3–6×）
_READ_CHUNK = 1024 * 1024  # 1 MB


def _official_dir(models_home: Path) -> Path:
    return models_home / "official_models"


def _model_ready(model_dir: Path) -> bool:
    if not model_dir.is_dir():
        return False
    has_w = any(model_dir.glob("*.pdiparams")) or any(model_dir.glob("*.safetensors"))
    has_cfg = (model_dir / "inference.yml").exists() or (model_dir / "config.json").exists()
    return has_w and has_cfg


def _format_speed(bps: float) -> str:
    mbps = bps / (1024 * 1024)
    if mbps >= 1.0:
        return f"{mbps:.1f} MB/s"
    return f"{bps / 1024:.0f} KB/s"


def _download_url(url: str, dest: Path, on_progress: ProgressFn, model: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "any2md/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        downloaded = 0
        last_pct = -1.0
        last_t = time.monotonic()
        speed_t = last_t
        speed_bytes = 0
        with dest.open("wb") as f:
            while True:
                chunk = resp.read(_READ_CHUNK)
                if not chunk:
                    break
                downloaded += len(chunk)
                speed_bytes += len(chunk)
                f.write(chunk)
                now = time.monotonic()
                dt = now - speed_t
                if dt >= 0.5:
                    speed = speed_bytes / dt if dt > 0 else 0.0
                    speed_bytes = 0
                    speed_t = now
                else:
                    speed = 0.0
                if total > 0:
                    pct = downloaded * 100.0 / total
                    if pct - last_pct >= 0.2 or now - last_t >= 0.5:
                        last_pct = pct
                        last_t = now
                        msg = f"下载 {model} … {pct:.1f}%"
                        if speed > 0:
                            msg += f" ({_format_speed(speed)})"
                        on_progress("download", msg, pct)


def _extract_tar(archive: Path, dest: Path, on_progress: ProgressFn, model: str) -> None:
    on_progress("download", f"解压 {model} …", 0.0)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        with tarfile.open(archive, "r:*") as tf:
            tf.extractall(tmp)
        entries = list(tmp.iterdir())
        src = entries[0] if len(entries) == 1 and entries[0].is_dir() else tmp
        if dest.exists():
            shutil.rmtree(dest)
        if src.is_dir():
            shutil.copytree(src, dest)
        else:
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest / src.name)
    on_progress("download", f"解压 {model} 完成", 100.0)


class _ProgressHub:
    """Thread-safe aggregate progress for parallel model downloads."""

    def __init__(self, model_ids: list[str], on_progress: ProgressFn) -> None:
        self._lock = threading.Lock()
        self._on_progress = on_progress
        self._model_ids = model_ids
        self._pct: dict[str, float] = {mid: 0.0 for mid in model_ids}
        self._done: set[str] = set()

    def update(self, model_id: str, message: str, pct: float | None) -> None:
        with self._lock:
            if pct is not None:
                self._pct[model_id] = pct
            total = len(self._model_ids)
            overall = sum(self._pct[mid] for mid in self._model_ids) / total
            self._on_progress("download", message, min(99.0, overall))

    def mark_done(self, model_id: str, label: str) -> None:
        with self._lock:
            self._pct[model_id] = 100.0
            self._done.add(model_id)
            total = len(self._model_ids)
            overall = sum(self._pct[mid] for mid in self._model_ids) / total
            self._on_progress("complete", f"{label} 完成", min(99.0, overall))


def _download_one(
    model_id: str,
    models_home: Path,
    hub: _ProgressHub,
) -> None:
    meta = CATALOG[model_id]
    name = meta["name"]
    dest = _official_dir(models_home) / name

    if _model_ready(dest):
        hub.mark_done(model_id, meta["label"])
        hub.update(model_id, f"{meta['label']} 已存在，跳过", 100.0)
        return

    url = f"{BOS_BASE}/{meta['tar']}"
    hub.update(model_id, f"开始下载 {meta['label']} …", 0.0)

    def wrap(_stage: str, msg: str, pct: float | None) -> None:
        hub.update(model_id, msg, pct)

    with tempfile.TemporaryDirectory() as td:
        archive = Path(td) / meta["tar"]
        try:
            _download_url(url, archive, wrap, name)
        except urllib.error.URLError as exc:
            raise RuntimeError(f"下载失败 {url}：{exc}") from exc
        _extract_tar(archive, dest, wrap, name)

    hub.mark_done(model_id, meta["label"])


def download_models(
    models_home: Path,
    model_ids: list[str],
    on_progress: ProgressFn,
) -> None:
    """Download selected models to models_home/official_models/."""
    if models_home.drive.upper() == "C:":
        raise RuntimeError("模型目录不能设在 C 盘")

    models_home.mkdir(parents=True, exist_ok=True)
    official = _official_dir(models_home)
    official.mkdir(parents=True, exist_ok=True)

    on_progress(
        "init",
        f"模型目录：{models_home}，下载源：BOS（多连接并行，约 2 GB）",
        0.0,
    )

    for mid in model_ids:
        if mid not in CATALOG:
            raise RuntimeError(f"未知模型：{mid}")

    hub = _ProgressHub(model_ids, on_progress)
    workers = min(2, len(model_ids))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_download_one, mid, models_home, hub): mid for mid in model_ids}
        for fut in as_completed(futures):
            mid = futures[fut]
            try:
                fut.result()
            except Exception as exc:
                raise RuntimeError(f"{CATALOG[mid]['label']}：{exc}") from exc

    on_progress("done", "全部模型下载完成", 100.0)
