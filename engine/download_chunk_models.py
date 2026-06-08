#!/usr/bin/env python3
"""Download semantic chunking models from ModelScope (domestic CDN)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from chunk_models import CATALOG, chunk_models_dir, model_dir
from model_paths import forbid_c_drive, resolve_models_home


def _emit(stage: str, message: str, **extra) -> None:
    payload = {"stage": stage, "message": message, **extra}
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr, flush=True)


def download_one(model_id: str, models_home: Path) -> Path:
    meta = CATALOG[model_id]
    dest = model_dir(models_home, model_id)
    if dest.is_dir() and any(dest.iterdir()):
        _emit("skip", f"{meta['label']} 已存在", model=model_id, path=str(dest))
        return dest

    try:
        from modelscope.hub.snapshot_download import snapshot_download
    except ImportError as exc:
        raise RuntimeError("请安装 modelscope：pip install modelscope") from exc

    _emit("start", f"开始下载 {meta['label']}（魔搭 ModelScope）", model=model_id)
    local = snapshot_download(
        meta["modelscope_id"],
        cache_dir=str(chunk_models_dir(models_home)),
        local_dir=str(dest),
    )
    _emit("complete", f"{meta['label']} 完成", model=model_id, path=str(local))
    return Path(local)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download any2md chunk embedding models")
    parser.add_argument("-m", "--models-dir", help="Model cache root (must not be on C:)")
    parser.add_argument(
        "--models",
        nargs="+",
        choices=list(CATALOG),
        default=[list(CATALOG)[0]],
    )
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    if args.list:
        items = [{"id": k, **{kk: vv for kk, vv in v.items()}} for k, v in CATALOG.items()]
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return 0

    home = resolve_models_home(args.models_dir)
    forbid_c_drive(home)
    chunk_models_dir(home).mkdir(parents=True, exist_ok=True)

    for mid in args.models:
        download_one(mid, home)

    _emit("done", "切分模型下载完成", models_home=str(home))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        _emit("error", str(exc))
        raise SystemExit(1) from exc
