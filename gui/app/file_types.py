"""Supported file types for the GUI."""

from __future__ import annotations

from pathlib import Path

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".gif"}
OFFICE_EXTS = {".docx", ".xlsx", ".xls", ".doc"}
PDF_EXTS = {".pdf"}

SUPPORTED_EXTS = PDF_EXTS | IMAGE_EXTS | OFFICE_EXTS

FILE_DIALOG_PATTERN = (
    "*.pdf;*.docx;*.doc;*.xlsx;*.xls;"
    "*.png;*.jpg;*.jpeg;*.bmp;*.tiff;*.webp;*.gif"
)

PARSE_MODE_LABELS: dict[str, str] = {
    "auto": "自动（推荐）",
    "text": "仅文本提取（最快）",
    "ocr": "强制 OCR（扫描增强）",
}

CHUNK_MODEL_LABELS: dict[str, str] = {
    "none": "关闭",
    "bge-base-zh-v1.5": "BGE-base-zh-v1.5（推荐）",
    "bge-large-zh-v1.5": "BGE-large-zh-v1.5（高质量）",
    "gte-large-zh": "GTE-large-zh（魔搭）",
}


def is_supported(path: Path | str) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_EXTS


def needs_paddle(path: Path | str, route: str) -> bool:
    ext = Path(path).suffix.lower()
    if route == "ocr":
        return True
    if route == "text":
        return ext in IMAGE_EXTS
    if ext in OFFICE_EXTS:
        return False
    if ext in IMAGE_EXTS or ext in PDF_EXTS:
        return True
    return False
