"""Semantic / structure chunking for Markdown → chunks.json + chunks/*.md."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import numpy as np

from chunk_models import CATALOG, DEFAULT_CHUNK_MODEL, model_dir, model_ready
from model_paths import early_models_dir_from_argv, resolve_models_home
from output_layout import OutputBatch


def _log_event(stage: str, message: str, **extra) -> None:
    print(f"[{stage}] {message}", file=sys.stderr, flush=True)
    print(json.dumps({"stage": stage, "message": message, **extra}, ensure_ascii=False), file=sys.stderr, flush=True)


def _split_sentences(text: str) -> list[str]:
    text = re.sub(r"\r\n?", "\n", text)
    paras = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    out: list[str] = []
    for para in paras:
        if re.match(r"^#{1,6}\s", para):
            out.append(para)
            continue
        parts = re.split(r"(?<=[。！？!?；;])\s*", para)
        for p in parts:
            p = p.strip()
            if p:
                out.append(p)
    return out or [text.strip()]


def _write_chunks(
    md_path: Path,
    chunks: list[str],
    *,
    model_id: str,
    mode: str,
    log_event,
) -> tuple[Path, Path]:
    stem = md_path.stem
    batch = OutputBatch.from_md_path(md_path)
    if batch:
        out_dir = batch.chunks_dir(stem)
        json_path = batch.chunks_json_path(stem)
    else:
        out_dir = md_path.parent / "chunks"
        json_path = md_path.parent / f"{stem}.chunks.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    chunk_md_files: list[str] = []
    records: list[dict] = []

    for idx, body in enumerate(chunks, start=1):
        name = f"{stem}_{idx:03d}.md"
        cp = out_dir / name
        cp.write_text(f"<!-- chunk {idx}/{len(chunks)} · {mode} -->\n\n{body}\n", encoding="utf-8")
        chunk_md_files.append(str(cp))
        records.append(
            {
                "id": idx,
                "index": idx - 1,
                "text": body,
                "source_md": str(md_path),
                "chunk_md": str(cp),
                "chars": len(body),
            }
        )

    json_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": str(md_path),
        "chunk_model": model_id,
        "chunk_mode": mode,
        "chunk_count": len(chunks),
        "chunks": records,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log_event(
        "done",
        f"切分完成：{len(chunks)} 块 → {json_path.name}",
        chunk_model=model_id,
        chunk_mode=mode,
        chunk_count=len(chunks),
        chunks_json=str(json_path),
        chunk_md_files=chunk_md_files,
    )
    return json_path, out_dir


def chunk_by_structure(md_path: Path, *, max_chars: int, log_event) -> tuple[Path, Path]:
    text = md_path.read_text(encoding="utf-8")
    sections = re.split(r"(?=^#{1,6}\s)", text, flags=re.MULTILINE)
    sections = [s.strip() for s in sections if s.strip()]
    if len(sections) <= 1:
        sections = re.split(
            r"(?=^[一二三四五六七八九十百]+[、．.]|\n\d+[\.、．]\s+\S)",
            text,
            flags=re.MULTILINE,
        )
        sections = [s.strip() for s in sections if s.strip()]
    if not sections:
        sections = [text.strip()]

    chunks: list[str] = []
    buf = ""
    for sec in sections:
        if not buf:
            buf = sec
        elif len(buf) + len(sec) + 2 <= max_chars:
            buf = f"{buf}\n\n{sec}"
        else:
            if buf:
                chunks.append(buf)
            if len(sec) <= max_chars:
                buf = sec
            else:
                for sent in _split_sentences(sec):
                    if len(sent) <= max_chars:
                        chunks.append(sent)
                    else:
                        for i in range(0, len(sent), max_chars):
                            chunks.append(sent[i : i + max_chars])
                buf = ""
    if buf:
        chunks.append(buf)

    log_event("chunk", f"结构切分（按标题/段落，{len(chunks)} 块）", chunk_mode="structure")
    return _write_chunks(md_path, chunks, model_id="structure", mode="structure", log_event=log_event)


def chunk_by_semantic(
    md_path: Path,
    *,
    models_home: Path,
    model_id: str,
    max_chars: int,
    log_event,
) -> tuple[Path, Path]:
    if not model_ready(models_home, model_id):
        raise RuntimeError(
            f"切分模型未下载：{model_id}\n"
            f"请运行：python engine/download_chunk_models.py -m {models_home} --models {model_id}"
        )
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError("缺少 sentence-transformers：pip install sentence-transformers") from exc

    local = model_dir(models_home, model_id)
    log_event("chunk", f"加载语义模型 {model_id}（CPU）…", chunk_model=model_id)
    t0 = time.perf_counter()
    model = SentenceTransformer(str(local), device="cpu")
    text = md_path.read_text(encoding="utf-8")
    sentences = _split_sentences(text)
    if not sentences:
        raise RuntimeError("Markdown 为空")

    buffer = 1
    combined: list[str] = []
    for i, _ in enumerate(sentences):
        lo = max(0, i - buffer)
        hi = min(len(sentences), i + buffer + 1)
        combined.append(" ".join(sentences[lo:hi]))

    log_event("chunk", f"计算语义向量（{len(sentences)} 段）…", chunk_model=model_id)
    embeddings = np.asarray(
        model.encode(combined, normalize_embeddings=True, show_progress_bar=False)
    )
    distances = [
        1.0 - float(np.dot(embeddings[i], embeddings[i + 1]))
        for i in range(len(embeddings) - 1)
    ]
    threshold = float(np.percentile(distances, 95)) if distances else 0.0
    breaks = {i + 1 for i, d in enumerate(distances) if d >= threshold}

    chunks: list[str] = []
    buf: list[str] = []
    for i, sent in enumerate(sentences):
        buf.append(sent)
        cur = "\n\n".join(buf)
        if (i + 1) in breaks or len(cur) >= max_chars:
            chunks.append(cur)
            buf = []
    if buf:
        chunks.append("\n\n".join(buf))

    log_event(
        "chunk",
        f"语义切分完成（{len(chunks)} 块，{time.perf_counter() - t0:.1f}s）",
        chunk_model=model_id,
        elapsed_s=round(time.perf_counter() - t0, 1),
    )
    return _write_chunks(md_path, chunks, model_id=model_id, mode="semantic", log_event=log_event)


def chunk_markdown(
    md_path: Path,
    *,
    models_home: Path,
    model_id: str = DEFAULT_CHUNK_MODEL,
    mode: str = "auto",
    log_event=_log_event,
) -> tuple[Path, Path]:
    """mode: semantic | structure | auto (semantic if model ready else structure)."""
    md_path = md_path.resolve()
    if not md_path.is_file():
        raise RuntimeError(f"文件不存在：{md_path}")
    if md_path.suffix.lower() != ".md":
        raise RuntimeError("仅支持 .md 文件")

    meta = CATALOG.get(model_id, {})
    max_chars = int(meta.get("max_chars") or 1500)

    if mode == "structure":
        return chunk_by_structure(md_path, max_chars=max_chars, log_event=log_event)

    if mode == "semantic":
        return chunk_by_semantic(
            md_path, models_home=models_home, model_id=model_id, max_chars=max_chars, log_event=log_event
        )

    # auto
    if model_id in CATALOG and model_ready(models_home, model_id):
        try:
            return chunk_by_semantic(
                md_path,
                models_home=models_home,
                model_id=model_id,
                max_chars=max_chars,
                log_event=log_event,
            )
        except Exception as exc:
            log_event("chunk", f"语义切分失败，回退结构切分：{exc}", chunk_mode="structure")
    else:
        log_event("chunk", "未检测到语义模型，使用结构切分（按标题/段落）", chunk_mode="structure")
    return chunk_by_structure(md_path, max_chars=max_chars, log_event=log_event)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="any2md-chunk", description="Markdown semantic chunking")
    p.add_argument("-i", "--input", required=True, help="Markdown 文件或目录")
    p.add_argument("-m", "--models-dir", default=None)
    p.add_argument(
        "--chunk-model",
        default=DEFAULT_CHUNK_MODEL,
        choices=[*CATALOG.keys()],
    )
    p.add_argument(
        "--mode",
        default="auto",
        choices=["auto", "semantic", "structure"],
        help="auto=有模型则语义，否则结构",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    from bootstrap import apply_engine_env

    apply_engine_env(early_models_dir_from_argv(argv))
    args = build_parser().parse_args(argv)
    home = resolve_models_home(args.models_dir)

    inp = Path(args.input).expanduser().resolve()
    if inp.is_dir() and (inp / "md").is_dir():
        paths = sorted((inp / "md").glob("*.md"))
    elif inp.is_dir():
        paths = sorted(p for p in inp.rglob("*.md") if p.parent.name != "chunks")
    else:
        paths = [inp]

    if not paths:
        _log_event("error", f"未找到 Markdown：{inp}")
        return 1

    _log_event("init", f"切分 {len(paths)} 个文件，模式={args.mode}，模型={args.chunk_model}")
    ok = 0
    for p in paths:
        if p.parent.name == "chunks":
            continue
        try:
            chunk_markdown(
                p,
                models_home=home,
                model_id=args.chunk_model,
                mode=args.mode,
                log_event=_log_event,
            )
            ok += 1
        except Exception as exc:
            _log_event("error", f"{p.name}：{exc}")
            return 1

    _log_event("done", f"全部完成，共 {ok} 个文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
