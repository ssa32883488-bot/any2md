#!/usr/bin/env python3
"""Check any2md / PaddleOCR-VL environment (NVIDIA GPU required)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from gpu_check import require_nvidia_gpu  # noqa: E402
from bootstrap import apply_engine_env, mirror_summary  # noqa: E402
from model_paths import official_models_dir, resolve_models_home  # noqa: E402

# Default models on repo drive, not C:; domestic mirrors before paddleocr import.
apply_engine_env(resolve_models_home())


def _dir_size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return total / (1024 * 1024)


def main() -> int:
    home = resolve_models_home()
    paddlex = official_models_dir(home)

    print("=== any2md 环境检查（仅 NVIDIA GPU）===\n")
    print(f"Python: {sys.version.split()[0]} ({sys.executable})")

    try:
        from importlib.metadata import version

        print(f"paddleocr: {version('paddleocr')}")
        from paddleocr import PaddleOCRVL  # noqa: F401

        print("PaddleOCRVL: 可导入")
    except ImportError as exc:
        print(f"paddleocr: 未安装 ({exc})")
        print("  运行: .\\scripts\\setup.ps1")
        return 1
    except OSError as exc:
        print(f"paddleocr 导入失败: {exc}")
        return 1

    try:
        device = require_nvidia_gpu()
        import paddle

        print(f"PaddlePaddle: {getattr(paddle, '__version__', '?')}")
        print(f"CUDA: 已启用")
        print(f"GPU 数量: {paddle.device.cuda.device_count()}")
        print(f"默认设备: {device}")
    except RuntimeError as exc:
        print(f"[失败] {exc}")
        return 1

    print(f"\n模型目录: {home}")
    print(f"权重缓存: {paddlex}")
    if paddlex.exists():
        found = False
        for d in sorted(paddlex.iterdir()):
            if d.is_dir():
                found = True
                print(f"  [已下载] {d.name}  ({_dir_size_mb(d):.1f} MB)")
        if not found:
            print("  (空 — 首次运行会自动下载)")
    else:
        print("  (尚未创建 — 首次运行会自动下载)")

    print("\n首次运行阶段：")
    print("  1. 下载 PP-DocLayoutV3（~200MB）")
    print("  2. 下载 PaddleOCR-VL（~1–2GB）")
    print("  3. GPU 加载模型 + 逐页推理")

    mirrors = mirror_summary()
    print(f"\n模型下载源: {mirrors['model_source']}（国内镜像，失败时回退 modelscope / aistudio / hf-mirror）")
    print(f"HF 镜像: {mirrors['hf_endpoint']}")

    disable = os.environ.get("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "")
    print(f"\nPADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK = {disable or '(未设置)'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
