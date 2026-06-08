"""Supported input formats and routing helpers."""

from __future__ import annotations

from pathlib import Path

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".gif"}
OFFICE_EXTS = {".docx", ".xlsx", ".xls", ".doc"}
PDF_EXTS = {".pdf"}

SUPPORTED_EXTS = PDF_EXTS | IMAGE_EXTS | OFFICE_EXTS

PARSE_MODES = ("auto", "text", "ocr", "force-text")


def suffix(path: Path | str) -> str:
    return Path(path).suffix.lower()


def is_supported(path: Path | str) -> bool:
    return suffix(path) in SUPPORTED_EXTS


def is_pdf(path: Path | str) -> bool:
    return suffix(path) in PDF_EXTS


def is_image(path: Path | str) -> bool:
    return suffix(path) in IMAGE_EXTS


def is_office(path: Path | str) -> bool:
    return suffix(path) in OFFICE_EXTS


def needs_gpu_ocr(path: Path | str, route: str) -> bool:
    """Whether PaddleOCR-VL is required for this file and route."""
    if route == "ocr":
        return True
    if route == "text" or route == "force-text":
        return is_image(path)
    # auto: office never needs GPU; images always; PDF decided later
    if is_office(path):
        return False
    if is_image(path):
        return True
    return is_pdf(path)
