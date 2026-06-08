"""Lightweight PDF helpers (no heavy deps)."""

from __future__ import annotations

import re
from pathlib import Path


def pdf_page_count(path: Path) -> int | None:
    """Best-effort page count from PDF structure."""
    try:
        raw = path.read_bytes()
    except OSError:
        return None

    for chunk in (raw[-16384:], raw[:65536]):
        text = chunk.decode("latin-1", errors="ignore")
        counts = [int(m) for m in re.findall(r"/Count\s+(\d+)", text)]
        if counts:
            return max(counts)

    n = len(re.findall(rb"/Type\s*/Page\b", raw))
    return n if n > 0 else None


def pdf_text_coverage(path: Path, *, sample_pages: int = 5, min_chars: int = 80) -> float:
    """
    Fraction of sampled pages with enough extractable text (0.0–1.0).
    Uses PyMuPDF when available; returns 0.0 if unavailable.
    """
    try:
        import fitz  # pymupdf
    except ImportError:
        return 0.0

    try:
        doc = fitz.open(path)
    except Exception:
        return 0.0

    try:
        total = len(doc)
        if total == 0:
            return 0.0
        indices = [
            int(i * (total - 1) / max(sample_pages - 1, 1)) for i in range(min(sample_pages, total))
        ]
        good = 0
        for i in indices:
            text = doc[i].get_text("text") or ""
            printable = sum(1 for c in text if c.isprintable() and not c.isspace())
            if printable >= min_chars:
                good += 1
        return good / len(indices)
    finally:
        doc.close()


def choose_pdf_route(path: Path, mode: str, *, text_threshold: float = 0.6) -> str:
    """
    Return 'text' or 'ocr' for a PDF given parse mode.
    mode: auto | text | ocr | force-text

    auto: digital text → structured CPU path; scan → OCR.
    Complex digital PDFs (tables/images) still use structured CPU path first;
    caller may fall back to OCR if output quality is insufficient.
    """
    if mode == "ocr":
        return "ocr"
    if mode in ("text", "force-text"):
        return "text"
    cov = pdf_text_coverage(path)
    return "text" if cov >= text_threshold else "ocr"
