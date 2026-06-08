#!/usr/bin/env python3
"""Download PaddleOCR-VL models from domestic BOS mirror with JSON progress."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tarfile
import tempfile
import time
from pathlib import Path

import requests

from bootstrap import apply_engine_env, mirror_summary
from model_paths import forbid_c_drive, official_models_dir, resolve_models_home

BOS_BASE = (
    "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0"
)

CATALOG: dict[str, dict] = {
    "PP-DocLayoutV3": {
        "name": "PP-DocLayoutV3",
        "label": "版面分析模型",
        "size_mb": 126,
        "tar": "PP-DocLayoutV3_infer.tar",
        "role": "layout",
    },
    "PaddleOCR-VL-1.6": {
        "name": "PaddleOCR-VL-1.6",
        "label": "文档语义 / VLM 模型",
        "size_mb": 1840,
        "tar": "PaddleOCR-VL-1.6_infer.tar",
        "role": "vlm",
    },
}


def _emit(stage: str, message: str, **extra) -> None:
    payload = {"stage": stage, "message": message, **extra}
    line = json.dumps(payload, ensure_ascii=False)
    print(line, file=sys.stderr, flush=True)


def _dir_size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return total / (1024 * 1024)


def _model_ready(model_dir: Path) -> bool:
    if not model_dir.is_dir():
        return False
    has_weights = any(model_dir.glob("*.pdiparams")) or any(model_dir.glob("*.safetensors"))
    has_config = (model_dir / "inference.yml").exists() or (model_dir / "config.json").exists()
    return has_weights and has_config and _dir_size_mb(model_dir) > 1.0


def _download_stream(url: str, dest: Path, model: str, phase: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=30) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length") or 0)
        downloaded = 0
        last_pct = -1.0
        last_t = 0.0
        with dest.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=256 * 1024):
                if not chunk:
                    continue
                downloaded += len(chunk)
                f.write(chunk)
                if total > 0:
                    pct = downloaded * 100.0 / total
                    now = time.monotonic()
                    if pct - last_pct >= 0.3 or now - last_t >= 0.4:
                        last_pct = pct
                        last_t = now
                        _emit(
                            "download",
                            f"下载 {model} … {pct:.1f}%",
                            model=model,
                            phase=phase,
                            percent=round(pct, 1),
                            downloaded=downloaded,
                            total=total,
                        )


def _extract_tar(archive: Path, model: str, dest: Path) -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        with tarfile.open(archive, "r:*") as tf:
            members = tf.getmembers()
            total = max(len(members), 1)
            for i, member in enumerate(members, 1):
                tf.extract(member, tmp)
                pct = i * 100.0 / total
                _emit(
                    "download",
                    f"解压 {model} … {pct:.0f}%",
                    model=model,
                    phase="extract",
                    percent=round(pct, 1),
                )
        entries = list(tmp.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            src = entries[0]
        else:
            src = tmp
        if dest.exists():
            shutil.rmtree(dest)
        if src.is_dir():
            shutil.copytree(src, dest)
        else:
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest / src.name)


def download_one(model_id: str, models_home: Path, *, force: bool = False) -> None:
    meta = CATALOG[model_id]
    name = meta["name"]
    dest = official_models_dir(models_home) / name
    if not force and _model_ready(dest):
        _emit("skip", f"{meta['label']} 已存在，跳过", model=name, percent=100.0)
        return

    url = f"{BOS_BASE}/{meta['tar']}"
    _emit("start", f"开始下载 {meta['label']}（约 {meta['size_mb']} MB）", model=name, percent=0.0)

    with tempfile.TemporaryDirectory() as td:
        archive = Path(td) / meta["tar"]
        _download_stream(url, archive, name, "download")
        _extract_tar(archive, name, dest)

    _emit(
        "complete",
        f"{meta['label']} 完成（{_dir_size_mb(dest):.0f} MB）",
        model=name,
        percent=100.0,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Download any2md models (domestic BOS mirror)")
    parser.add_argument(
        "--models-dir",
        "-m",
        help="Model cache root (must not be on C:)",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        choices=list(CATALOG),
        default=list(CATALOG),
        help="Models to download",
    )
    parser.add_argument("--force", action="store_true", help="Re-download even if present")
    parser.add_argument("--list", action="store_true", help="Print catalog JSON and exit")
    args = parser.parse_args()

    if args.list:
        items = [
            {"id": k, **{kk: vv for kk, vv in v.items() if kk != "tar"}}
            for k, v in CATALOG.items()
        ]
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return 0

    home = apply_engine_env(args.models_dir)
    mirrors = mirror_summary()
    _emit(
        "init",
        f"模型目录：{home}，下载源：{mirrors['model_source']}",
        models_home=str(home),
        **mirrors,
    )

    total = len(args.models)
    for i, model_id in enumerate(args.models, 1):
        _emit("progress", f"模型 {i}/{total}", index=i, total=total, model=model_id)
        download_one(model_id, home, force=args.force)

    _emit("done", "全部模型下载完成", models_home=str(home))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        _emit("error", str(exc))
        raise SystemExit(1) from exc
