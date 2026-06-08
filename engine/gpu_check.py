"""NVIDIA GPU requirement checks."""

from __future__ import annotations


def require_nvidia_gpu(device: str | None = None) -> str:
    """Return GPU device string or raise RuntimeError."""
    if device:
        normalized = device.strip().lower()
        if normalized == "cpu" or normalized.startswith("cpu:"):
            raise RuntimeError(
                "any2md 不支持 CPU 推理。请安装 NVIDIA 显卡与 paddlepaddle-gpu，"
                "然后运行 .\\scripts\\setup.ps1"
            )
        if not (normalized.startswith("gpu") or normalized.startswith("cuda")):
            raise RuntimeError(f"不支持的设备：{device}（仅支持 NVIDIA GPU，如 gpu:0）")
        return device

    try:
        import paddle
    except ImportError as exc:
        raise RuntimeError(
            "未安装 PaddlePaddle GPU 版。请运行：.\\scripts\\setup.ps1"
        ) from exc

    if not paddle.device.is_compiled_with_cuda():
        raise RuntimeError(
            "当前 PaddlePaddle 不是 GPU 版（无 CUDA 支持）。"
            "请运行 .\\scripts\\setup.ps1 安装 paddlepaddle-gpu"
        )

    try:
        count = paddle.device.cuda.device_count()
    except Exception as exc:
        raise RuntimeError(f"无法检测 NVIDIA GPU：{exc}") from exc

    if count < 1:
        raise RuntimeError(
            "未检测到可用的 NVIDIA GPU。any2md 需要 NVIDIA 显卡才能运行。"
        )

    return "gpu:0"
