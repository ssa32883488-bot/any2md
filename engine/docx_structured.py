"""Structured Word → Markdown: preserve document order, headings, nested tables."""

from __future__ import annotations

import re
from typing import Iterator

from docx.document import Document as DocxDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph

_RE_CN_L1 = re.compile(r"^[一二三四五六七八九十百]+[、．.]")
_RE_NUM_HEAD = re.compile(r"^\d+[\.．]\s+\S")
_RE_CN_LIST = re.compile(r"^(\d+)[、](?:\s*)")
_RE_LIST = re.compile(r"^(\d+)[\.．](?:\s+)")


def iter_block_items(parent) -> Iterator[Paragraph | Table]:
    if isinstance(parent, DocxDocument):
        parent_elm = parent.element.body
    elif isinstance(parent, _Cell):
        parent_elm = parent._tc
    else:
        raise ValueError(f"unsupported parent: {type(parent)!r}")

    for child in parent_elm.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)


def _outline_level(para: Paragraph) -> int | None:
    p_pr = para._element.pPr
    if p_pr is not None and p_pr.outlineLvl is not None:
        return int(p_pr.outlineLvl.val)
    try:
        style = para.style
        if style is not None and style.element.pPr is not None:
            ol = style.element.pPr.outlineLvl
            if ol is not None:
                return int(ol.val)
    except Exception:
        pass
    return None


def _style_heading_level(para: Paragraph) -> int | None:
    name = (para.style.name or "").lower().replace(" ", "")
    if not name:
        return None
    if name in ("title", "标题"):
        return 1
    for n in range(1, 10):
        if name in (f"heading{n}", f"标题{n}"):
            return n
    if "heading" in name or "标题" in name:
        for n in range(1, 10):
            if str(n) in name:
                return n
        return 3
    return None


def _bold_short_heading(para: Paragraph) -> bool:
    text = para.text.strip()
    if not text or len(text) > 72:
        return False
    runs = [r for r in para.runs if r.text.strip()]
    if not runs:
        return False
    return all(r.bold for r in runs)


def _heading_md(para: Paragraph) -> str | None:
    text = para.text.strip()
    if not text:
        return None

    lvl = _outline_level(para)
    if lvl is None:
        lvl = _style_heading_level(para)

    if lvl is not None:
        return "#" * min(lvl + 1, 6)

    if _RE_CN_L1.match(text):
        return "##"
    if _RE_NUM_HEAD.match(text) and len(text) <= 80:
        return "###"
    if _bold_short_heading(para) and not _RE_CN_LIST.match(text):
        return "###"
    return None


def _para_to_md(para: Paragraph) -> str | None:
    text = para.text.strip()
    if not text:
        return None

    prefix = _heading_md(para)
    if prefix:
        return f"{prefix} {text}"

    m = _RE_CN_LIST.match(text)
    if m:
        body = text[m.end() :].strip()
        return f"{m.group(1)}. {body}" if body else text

    m = _RE_LIST.match(text)
    if m:
        body = text[m.end() :].strip()
        return f"{m.group(1)}. {body}" if body else text

    return text


def _cell_text_len(cell: _Cell) -> int:
    n = 0
    for block in iter_block_items(cell):
        if isinstance(block, Paragraph):
            n += len(block.text)
        elif isinstance(block, Table):
            n += _table_text_len(block)
    return n


def _table_text_len(table: Table) -> int:
    seen: set[int] = set()
    total = 0
    for row in table.rows:
        for cell in row.cells:
            tc_id = id(cell._tc)
            if tc_id in seen:
                continue
            seen.add(tc_id)
            total += _cell_text_len(cell)
    return total


def _table_cell_stats(table: Table) -> tuple[list[int], list[int]]:
    para_counts: list[int] = []
    lengths: list[int] = []
    seen: set[int] = set()
    for row in table.rows:
        for cell in row.cells:
            tc_id = id(cell._tc)
            if tc_id in seen:
                continue
            seen.add(tc_id)
            pc = 0
            clen = 0
            for block in iter_block_items(cell):
                if isinstance(block, Paragraph):
                    t = block.text.strip()
                    if t:
                        pc += 1
                        clen += len(t)
                elif isinstance(block, Table):
                    nested_len = _table_text_len(block)
                    clen += nested_len
                    if nested_len:
                        pc += 1
            para_counts.append(pc)
            lengths.append(clen)
    return para_counts, lengths


def _is_layout_table(table: Table) -> bool:
    para_counts, lengths = _table_cell_stats(table)
    if not para_counts:
        return True

    total_paras = sum(para_counts)
    max_paras = max(para_counts)
    unique_cells = len(para_counts)
    avg_len = sum(lengths) / max(unique_cells, 1)

    # Single cell holding multiple paragraphs → layout wrapper (common in WPS/Word templates)
    if unique_cells == 1 and total_paras >= 2:
        return True
    if max_paras >= 3 and max_paras / max(total_paras, 1) >= 0.45:
        return True

    # Grid with short single-line cells → real data table
    if unique_cells >= 4 and max_paras <= 1 and avg_len < 150:
        return False
    if unique_cells >= 2 and max_paras <= 2 and avg_len < 100 and total_paras <= unique_cells * 2:
        return False

    total_text = sum(lengths)
    if total_text > 500 and max_paras >= 2:
        return True
    return unique_cells <= 2 and total_text > 180


def _table_to_markdown(table: Table) -> str:
    rows: list[list[str]] = []
    seen_rows: set[tuple[str, ...]] = set()
    for row in table.rows:
        cells: list[str] = []
        seen_tc: set[int] = set()
        for cell in row.cells:
            tc_id = id(cell._tc)
            if tc_id in seen_tc:
                continue
            seen_tc.add(tc_id)
            cells.append(cell.text.replace("\n", " ").strip())
        key = tuple(cells)
        if key in seen_rows:
            continue
        seen_rows.add(key)
        if any(cells):
            rows.append(cells)

    if not rows:
        return ""

    width = max(len(r) for r in rows)
    lines = ["| " + " | ".join(r + [""] * (width - len(r))) + " |" for r in rows]
    if len(lines) >= 1 and width >= 1:
        sep = "| " + " | ".join(["---"] * width) + " |"
        lines = [lines[0], sep, *lines[1:]]
    return "\n".join(lines)


def _blocks_from_parent(parent) -> list[str]:
    parts: list[str] = []
    for block in iter_block_items(parent):
        if isinstance(block, Paragraph):
            md = _para_to_md(block)
            if md:
                parts.append(md)
        else:
            parts.extend(_blocks_from_table(block))
    return parts


def _blocks_from_table(table: Table) -> list[str]:
    if _is_layout_table(table):
        parts: list[str] = []
        seen: set[int] = set()
        for row in table.rows:
            for cell in row.cells:
                tc_id = id(cell._tc)
                if tc_id in seen:
                    continue
                seen.add(tc_id)
                parts.extend(_blocks_from_parent(cell))
        return parts
    md = _table_to_markdown(table)
    return [md] if md else []


def docx_to_markdown_body(doc: DocxDocument, *, title: str) -> str:
    parts = [f"# {title}"]
    parts.extend(_blocks_from_parent(doc))
    return "\n\n".join(parts) + "\n"
