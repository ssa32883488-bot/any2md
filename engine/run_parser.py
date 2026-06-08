#!/usr/bin/env python3
"""
Document → Markdown router (Path B engine).

Routes by file type and --route:
  auto     — digital PDF / Office → CPU fast path; scan/image → PaddleOCR-VL GPU
  text     — CPU fast path when possible
  ocr      — always GPU OCR
  force-text — same as text (legacy alias)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from bootstrap import apply_engine_env
from model_paths import early_models_dir_from_argv

# DLL search paths must be set before paddleocr/torch import chain
apply_engine_env(early_models_dir_from_argv())

from chunk_models import DEFAULT_CHUNK_MODEL
from fast_parser import can_fast_convert, convert_fast
from file_types import is_image, is_office, is_pdf, suffix
from model_paths import resolve_models_home
from output_layout import OutputBatch
from ocr_parser import run_ocr
from pdf_utils import choose_pdf_route, pdf_page_count
from pdf_structured import pdf_needs_rich_layout


def _say(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _log_event(stage: str, message: str, **extra) -> None:
    _say(f"[{stage}] {message}")
    payload = {"stage": stage, "message": message, **extra}
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr, flush=True)


def _resolve_route(input_path: Path, mode: str) -> str:
    if is_image(input_path):
        return "ocr" if mode in ("auto", "ocr") else "ocr"
    if is_office(input_path):
        return "text"
    if is_pdf(input_path):
        if mode == "ocr":
            return "ocr"
        if mode in ("text", "force-text"):
            return "text"
        return choose_pdf_route(input_path, mode)
    return "ocr"


def _maybe_chunk(md_paths: list[str], args: argparse.Namespace, models_home: Path) -> None:
    if not args.chunk_model or args.chunk_model == "none":
        return
    from run_chunker import chunk_markdown

    for md in md_paths:
        chunk_markdown(
            Path(md),
            models_home=models_home,
            model_id=args.chunk_model,
            mode="auto",
            log_event=_log_event,
        )


def _run(args: argparse.Namespace) -> int:
    if args.models_dir:
        apply_engine_env(args.models_dir)
    models_home = resolve_models_home(args.models_dir)

    input_path = Path(args.input).expanduser()
    if str(args.input).startswith(("http://", "https://")):
        _log_event("error", "URL 输入暂仅支持 OCR 路径，请使用 --route ocr")
        return 1

    input_path = input_path.resolve()
    if not input_path.exists():
        _log_event("error", f"输入文件不存在：{input_path}")
        return 1

    output_arg = Path(args.output).expanduser().resolve()
    batch = OutputBatch.resolve(output_arg)
    _log_event("init", f"输出批次：{batch.root.name}", **batch.summary())

    route = _resolve_route(input_path, args.route)
    _log_event(
        "route",
        f"解析模式：{args.route} → 实际路径 {route.upper()}（{input_path.name}）",
        route=route,
        parse_mode=args.route,
        file=input_path.name,
    )

    t0 = time.perf_counter()
    md_paths: list[str] = []

    if route == "text":
        if not can_fast_convert(input_path) and is_pdf(input_path):
            _log_event("init", "未安装 pymupdf/docx/openpyxl，回退 OCR 路径", route="ocr")
            route = "ocr"
        else:
            try:
                out_md = convert_fast(input_path, batch, _log_event)
                md_paths = [str(out_md)]
                # auto: structured output too thin on complex PDF → OCR fallback
                if (
                    args.route == "auto"
                    and is_pdf(input_path)
                    and pdf_needs_rich_layout(input_path)
                ):
                    text = out_md.read_text(encoding="utf-8")
                    pages = pdf_page_count(input_path) or 1
                    if len(text.strip()) < pages * 120:
                        _log_event(
                            "init",
                            "结构化提取结果过短，自动回退 GPU OCR 以保留版式",
                            route="ocr",
                        )
                        route = "ocr"
                        md_paths = []
            except Exception as exc:
                if args.route == "auto" and is_pdf(input_path):
                    _log_event("init", f"快路径失败，回退 OCR：{exc}", route="ocr")
                    route = "ocr"
                else:
                    raise

    if route == "ocr":
        md_paths = run_ocr(args, input_path, batch, _log_event)

    if not md_paths:
        _log_event("error", f"未生成 Markdown：{batch.root}")
        return 1

    if args.chunk_model and args.chunk_model != "none":
        _maybe_chunk(md_paths, args, models_home)

    total = time.perf_counter() - t0
    _log_event(
        "done",
        f"全部完成，总耗时 {total:.1f}s",
        **batch.summary(),
        markdown_files=md_paths,
        route=route,
        elapsed_s=round(total, 1),
    )
    print(
        json.dumps(
            {"output_dir": str(batch.root), "markdown_files": md_paths, **batch.summary()},
            ensure_ascii=False,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="any2md")
    p.add_argument("-i", "--input", required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("-m", "--models-dir", default=None, help="模型目录（禁止 C 盘）")
    p.add_argument(
        "--route",
        default="auto",
        choices=["auto", "text", "ocr", "force-text"],
        help="解析路由：auto=智能选择",
    )
    p.add_argument(
        "--chunk-model",
        default="none",
        choices=["none", "bge-base-zh-v1.5", "bge-large-zh-v1.5", "gte-large-zh"],
        help="语义切分模型（none=关闭）",
    )
    p.add_argument("--pipeline-version", default="v1.6", choices=["v1", "v1.5", "v1.6"])
    p.add_argument("--device", default=None, help="NVIDIA GPU，默认 gpu:0")
    p.add_argument("--layout-model-dir", default=None)
    p.add_argument("--vl-model-dir", default=None)
    p.add_argument("--use-unwarping", action="store_true")
    p.add_argument("--use-orientation", action="store_true")
    p.add_argument("--no-merge-tables", action="store_true")
    p.add_argument("--no-relevel-titles", action="store_true")
    p.add_argument("--no-concatenate-pages", action="store_true")
    p.add_argument("--save-json", action="store_true")
    p.add_argument("--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.merge_tables = not args.no_merge_tables
    args.relevel_titles = not args.no_relevel_titles
    args.concatenate_pages = not args.no_concatenate_pages
    if args.chunk_model == "default":
        args.chunk_model = DEFAULT_CHUNK_MODEL
    try:
        return _run(args)
    except KeyboardInterrupt:
        _log_event("error", "用户取消")
        return 130
    except Exception as exc:
        _log_event("error", str(exc))
        if args.verbose:
            raise
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
