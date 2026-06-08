#!/usr/bin/env python3
"""Rasterize digital PDFs into scan-like PDFs for OCR stress testing."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = ROOT / "testset" / "digital"
DEFAULT_OUT = ROOT / "testset" / "scan"


def pdf_to_scan_pdf(src: Path, dest: Path, *, dpi: int = 150) -> None:
    import fitz

    src_doc = fitz.open(src)
    out = fitz.open()
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)

    for page in src_doc:
        pix = page.get_pixmap(matrix=mat, alpha=False)
        rect = fitz.Rect(0, 0, pix.width, pix.height)
        new_page = out.new_page(width=rect.width, height=rect.height)
        new_page.insert_image(rect, pixmap=pix)

    src_doc.close()
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.save(dest, deflate=True, garbage=3)
    out.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Create scan-like PDFs from digital PDFs")
    parser.add_argument("-i", "--input", type=Path, default=DEFAULT_SRC)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--suffix", default="_scan")
    args = parser.parse_args()

    src_dir = args.input.expanduser().resolve()
    out_dir = args.output.expanduser().resolve()
    if not src_dir.is_dir():
        print(f"Source not found: {src_dir}", file=sys.stderr)
        print("Run: python scripts/generate_testset.py", file=sys.stderr)
        return 1

    pdfs = sorted(src_dir.glob("*.pdf"))
    if not pdfs:
        print(f"No PDF in {src_dir}", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    for pdf in pdfs:
        dest = out_dir / f"{pdf.stem}{args.suffix}.pdf"
        pdf_to_scan_pdf(pdf, dest, dpi=args.dpi)
        print(f"OK {dest.name} ({dest.stat().st_size // 1024} KB)")

    print(f"\nDone -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
