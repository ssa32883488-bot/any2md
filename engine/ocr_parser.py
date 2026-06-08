"""PaddleOCR-VL GPU path (scan / image / OCR PDF)."""

from __future__ import annotations

import time
from pathlib import Path

from bootstrap import apply_engine_env, mirror_summary
from gpu_check import require_nvidia_gpu
from model_paths import official_models_dir, resolve_models_home
from pdf_utils import pdf_page_count


def _log_model_cache_hint(models_home: Path, log_event) -> None:
    cache = official_models_dir(models_home)
    mirrors = mirror_summary()
    if cache.exists() and any(cache.iterdir()):
        log_event("models", f"已有本地模型：{cache}", **mirrors)
    else:
        log_event(
            "models",
            f"首次运行需下载模型（版面 ~200MB + VLM ~1–2GB），源：{mirrors['model_source']}",
            models_home=str(models_home),
            official_models=str(cache),
            **mirrors,
        )


def build_pipeline(args, log_event):
    from bootstrap import apply_engine_env

    apply_engine_env(args.models_dir)
    from paddleocr import PaddleOCRVL

    kwargs: dict = {
        "pipeline_version": args.pipeline_version,
        "device": args.device,
    }
    if args.layout_model_dir:
        kwargs["layout_detection_model_dir"] = args.layout_model_dir
    if args.vl_model_dir:
        kwargs["vl_rec_model_dir"] = args.vl_model_dir
    if args.use_unwarping:
        kwargs["use_doc_unwarping"] = True
    if args.use_orientation:
        kwargs["use_doc_orientation_classify"] = True

    models_home = resolve_models_home(args.models_dir)
    apply_engine_env(models_home)
    _log_model_cache_hint(models_home, log_event)
    log_event(
        "init",
        f"正在初始化 PaddleOCR-VL（{args.pipeline_version}，{args.device}）…",
        models_home=str(models_home),
        device=args.device,
        route="ocr",
    )
    t0 = time.perf_counter()
    pipeline = PaddleOCRVL(**kwargs)
    log_event(
        "init",
        f"引擎就绪，耗时 {time.perf_counter() - t0:.1f}s",
        device=args.device,
        elapsed_s=round(time.perf_counter() - t0, 1),
        route="ocr",
    )
    return pipeline


def predict_with_progress(pipeline, source: str, log_event, total_pages: int | None = None) -> list:
    predict_iter = getattr(pipeline, "predict_iter", None)
    if predict_iter is None:
        log_event("predict", "正在解析，请耐心等待…", total_pages=total_pages, route="ocr")
        return list(pipeline.predict(source))

    pages = []
    t0 = time.perf_counter()
    for page in predict_iter(source):
        pages.append(page)
        n = len(pages)
        log_event(
            "predict",
            f"已完成第 {n} 页" + (f"/{total_pages}" if total_pages else ""),
            page=n,
            total_pages=total_pages,
            elapsed_s=round(time.perf_counter() - t0, 1),
            route="ocr",
        )
    return pages


from output_layout import OutputBatch


def run_ocr(args, input_path: Path, batch: OutputBatch, log_event) -> list[str]:
    args.device = require_nvidia_gpu(args.device)
    pipeline = build_pipeline(args, log_event)

    source = str(input_path)
    is_pdf = input_path.suffix.lower() == ".pdf"
    total_pages = pdf_page_count(input_path) if is_pdf else 1
    log_event(
        "predict",
        f"开始 OCR 解析：{input_path.name}",
        total_pages=total_pages,
        file=input_path.name,
        route="ocr",
    )
    t0 = time.perf_counter()
    pages = predict_with_progress(pipeline, source, log_event, total_pages=total_pages)
    log_event(
        "predict",
        f"解析完成，共 {len(pages)} 页，耗时 {time.perf_counter() - t0:.1f}s",
        pages=len(pages),
        elapsed_s=round(time.perf_counter() - t0, 1),
        route="ocr",
    )

    if (
        is_pdf
        and len(pages) > 1
        and (args.merge_tables or args.relevel_titles or args.concatenate_pages)
    ):
        log_event("restructure", "合并跨页表格、重建标题层级…", route="ocr")
        results = list(
            pipeline.restructure_pages(
                pages,
                merge_tables=args.merge_tables,
                relevel_titles=args.relevel_titles,
                concatenate_pages=args.concatenate_pages,
            )
        )
    else:
        results = pages

    md_paths: list[str] = []
    stage = batch.ocr_stage_dir(input_path.stem)

    for idx, res in enumerate(results, start=1):
        log_event("save", f"保存 Markdown {idx}/{len(results)} → {batch.root / 'md'}", route="ocr")
        res.save_to_markdown(save_path=str(stage))
        if args.save_json:
            res.save_to_json(save_path=str(stage))

    collected = batch.collect_ocr_outputs(input_path.stem, stage)
    md_paths.extend(str(p) for p in collected)
    return sorted(md_paths)
