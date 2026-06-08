"""NVIDIA GPU detection without importing Paddle (first-run wizard)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass


# Known weak / unsupported patterns (pre-Volta or very low VRAM)
_UNSUPPORTED_PATTERNS = (
    r"GTX\s*9\d{2}",
    r"GTX\s*750",
    r"GT\s*\d",
    r"M\s*1200",  # mobile weak
    r"Quadro\s*K",
)
_MIN_VRAM_MB = 4096
_RECOMMENDED_VRAM_MB = 6144


@dataclass
class GpuInfo:
    ok: bool
    name: str
    vram_mb: int
    driver: str
    reason: str
    recommended: bool


def _parse_nvidia_smi() -> GpuInfo | None:
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None

    line = out.strip().splitlines()[0] if out.strip() else ""
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 3:
        return None

    name, vram_raw, driver = parts[0], parts[1], parts[2]
    try:
        vram_mb = int(float(vram_raw))
    except ValueError:
        vram_mb = 0

    return _evaluate(name, vram_mb, driver)


def _parse_wmic() -> GpuInfo | None:
    try:
        out = subprocess.check_output(
            [
                "wmic",
                "path",
                "win32_VideoController",
                "get",
                "Name,AdapterRAM",
                "/format:csv",
            ],
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None

    for line in out.splitlines():
        if "NVIDIA" not in line.upper():
            continue
        parts = line.split(",")
        if len(parts) < 3:
            continue
        name = parts[-2].strip()
        try:
            vram_bytes = int(parts[-1].strip() or "0")
            vram_mb = max(vram_bytes // (1024 * 1024), 0)
        except ValueError:
            vram_mb = 0
        if name:
            return _evaluate(name, vram_mb, "")

    return None


def _evaluate(name: str, vram_mb: int, driver: str) -> GpuInfo:
    upper = name.upper()
    if "NVIDIA" not in upper:
        return GpuInfo(False, name, vram_mb, driver, "未检测到 NVIDIA 显卡", False)

    for pat in _UNSUPPORTED_PATTERNS:
        if re.search(pat, name, re.I):
            return GpuInfo(
                False,
                name,
                vram_mb,
                driver,
                f"显卡 {name} 算力或显存偏低，不建议运行 PaddleOCR-VL",
                False,
            )

    if 0 < vram_mb < _MIN_VRAM_MB:
        return GpuInfo(
            False,
            name,
            vram_mb,
            driver,
            f"显存 {vram_mb} MB 不足（至少需要 {_MIN_VRAM_MB // 1024} GB）",
            False,
        )

    recommended = vram_mb >= _RECOMMENDED_VRAM_MB or vram_mb == 0
    reason = "适合运行 any2md（NVIDIA GPU）"
    if vram_mb and vram_mb < _RECOMMENDED_VRAM_MB:
        reason = f"可以运行，但显存 {vram_mb} MB 偏紧，建议关闭其他占 GPU 的程序"

    return GpuInfo(True, name, vram_mb, driver, reason, recommended)


def probe_gpu() -> GpuInfo:
    info = _parse_nvidia_smi()
    if info is None:
        info = _parse_wmic()
    if info is None:
        return GpuInfo(
            False,
            "",
            0,
            "",
            "未检测到 NVIDIA 显卡或驱动未安装（需要 nvidia-smi / 官方驱动）",
            False,
        )
    return info


def main() -> int:
    info = probe_gpu()
    if "--json" in sys.argv:
        print(json.dumps(asdict(info), ensure_ascii=False, indent=2))
    else:
        status = "通过" if info.ok else "不通过"
        print(f"[{status}] {info.name or '无'} — {info.reason}")
        if info.vram_mb:
            print(f"  显存: {info.vram_mb} MB")
        if info.driver:
            print(f"  驱动: {info.driver}")
    return 0 if info.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
