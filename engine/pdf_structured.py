"""Structured digital-PDF extraction: headings, tables, images (CPU, PyMuPDF)."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class _Elem:
    y0: float
    x0: float
    kind: str  # heading | para | table | image
    content: str


def _rect_overlap(a: tuple, b: tuple, tol: float = 2.0) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (ax1 < bx0 - tol or bx1 < ax0 - tol or ay1 < by0 - tol or by1 < ay0 - tol)


def _inside_any(bbox: tuple, boxes: list[tuple]) -> bool:
    cx = (bbox[0] + bbox[2]) / 2
    cy = (bbox[1] + bbox[3]) / 2
    for b in boxes:
        if b[0] <= cx <= b[2] and b[1] <= cy <= b[3]:
            return True
    return False


def _heading_map(body_sizes: list[float]) -> dict[str, str]:
    """Map representative font size → markdown heading prefix."""
    if not body_sizes:
        return {}

    body = statistics.median(body_sizes)
    candidates = sorted({round(s, 1) for s in body_sizes if s > body * 1.08}, reverse=True)
    levels = ["##", "###", "####", "#####"]
    mapping: dict[str, str] = {}
    for i, sz in enumerate(candidates[: len(levels)]):
        mapping[str(sz)] = levels[i]
    return mapping


def _line_heading(prefix: str | None, text: str) -> str:
    if prefix:
        return f"{prefix} {text}"
    return text


def pdf_to_markdown_structured(
    path: Path,
    md_path: Path,
    assets_dir: Path,
    log_event: Callable[..., None],
) -> Path:
    import fitz

    doc = fitz.open(path)
    assets_dir.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        body_sizes: list[float] = []
        for page in doc:
            blocks = page.get_text("dict").get("blocks", [])
            for block in blocks:
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    if not spans:
                        continue
                    text = "".join(s.get("text", "") for s in spans).strip()
                    if not text:
                        continue
                    body_sizes.append(max(s.get("size") or 12 for s in spans))

        hmap = _heading_map(body_sizes)
        parts: list[str] = [f"# {path.stem}\n"]
        total = len(doc)
        img_counter = 0

        for pi in range(total):
            page = doc[pi]
            elems: list[_Elem] = []
            table_boxes: list[tuple] = []

            # --- tables ---
            try:
                finder = page.find_tables()
                for ti, tab in enumerate(finder.tables):
                    md = tab.to_markdown().strip()
                    if not md:
                        continue
                    bbox = tab.bbox
                    table_boxes.append(bbox)
                    elems.append(_Elem(bbox[1], bbox[0], "table", md))
            except Exception:
                pass

            # --- images ---
            seen_xrefs: set[int] = set()
            for img in page.get_images(full=True):
                xref = int(img[0])
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)
                try:
                    info = doc.extract_image(xref)
                except Exception:
                    continue
                ext = info.get("ext") or "png"
                img_counter += 1
                name = f"page{pi + 1:03d}_img{img_counter:03d}.{ext}"
                img_path = assets_dir / name
                img_path.write_bytes(info["image"])
                rel = Path(img_path).relative_to(md_path.parent).as_posix()
                # approximate position from image rects on page
                rects = page.get_image_rects(xref)
                y0 = rects[0].y0 if rects else pi * 1000
                x0 = rects[0].x0 if rects else 0
                elems.append(_Elem(y0, x0, "image", f"![{name}]({rel})"))

            # --- text blocks (skip text inside tables) ---
            blocks = page.get_text("dict").get("blocks", [])
            for block in blocks:
                if block.get("type") != 0:
                    continue
                bbox = tuple(block.get("bbox", (0, 0, 0, 0)))
                if table_boxes and _inside_any(bbox, table_boxes):
                    continue
                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    if not spans:
                        continue
                    text = "".join(s.get("text", "") for s in spans).strip()
                    if not text:
                        continue
                    size = round(max(s.get("size") or 12 for s in spans), 1)
                    lb = line.get("bbox", bbox)
                    prefix = hmap.get(str(size))
                    kind = "heading" if prefix else "para"
                    elems.append(
                        _Elem(lb[1], lb[0], kind, _line_heading(prefix, text))
                    )

            elems.sort(key=lambda e: (e.y0, e.x0))
            if elems:
                if total > 1:
                    parts.append(f"\n<!-- page {pi + 1} -->\n")
                for el in elems:
                    if el.kind == "table":
                        parts.append(el.content)
                    elif el.kind == "image":
                        parts.append(el.content)
                    else:
                        parts.append(el.content)

            log_event(
                "predict",
                f"结构化提取第 {pi + 1}/{total} 页（含表格/图片）",
                page=pi + 1,
                total_pages=total,
                route="text",
            )

        body = "\n\n".join(parts) + "\n"
    finally:
        doc.close()

    out = md_path
    out.write_text(body, encoding="utf-8")
    return out


def pdf_layout_complexity(path: Path) -> dict:
    """Heuristic: does this digital PDF need OCR for layout fidelity?"""
    import fitz

    stats = {"pages": 0, "tables": 0, "images": 0, "text_chars": 0}
    doc = fitz.open(path)
    try:
        stats["pages"] = len(doc)
        for page in doc:
            stats["text_chars"] += len(page.get_text("text") or "")
            stats["images"] += len(page.get_images())
            try:
                stats["tables"] += len(page.find_tables().tables)
            except Exception:
                pass
    finally:
        doc.close()
    return stats


def pdf_needs_rich_layout(path: Path) -> bool:
    """True when PDF has meaningful tables/images but still has extractable text."""
    c = pdf_layout_complexity(path)
    if c["text_chars"] < 200:
        return False
    per_page_img = c["images"] / max(c["pages"], 1)
    per_page_tbl = c["tables"] / max(c["pages"], 1)
    return c["tables"] >= 1 or per_page_img >= 0.5
