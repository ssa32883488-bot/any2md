"""Semantic chunking embedding model catalog (ModelScope / hf-mirror)."""

from __future__ import annotations

from pathlib import Path

CATALOG: dict[str, dict] = {
    "bge-base-zh-v1.5": {
        "label": "BGE-base-zh-v1.5（推荐，~400MB）",
        "modelscope_id": "BAAI/bge-base-zh-v1.5",
        "size_mb": 400,
        "max_chars": 1500,
    },
    "bge-large-zh-v1.5": {
        "label": "BGE-large-zh-v1.5（高质量，~1.3GB）",
        "modelscope_id": "BAAI/bge-large-zh-v1.5",
        "size_mb": 1300,
        "max_chars": 1500,
    },
    "gte-large-zh": {
        "label": "GTE-large-zh（魔搭，~650MB）",
        "modelscope_id": "iic/nlp_gte_sentence-embedding_chinese-large",
        "size_mb": 650,
        "max_chars": 1500,
    },
}

DEFAULT_CHUNK_MODEL = "bge-base-zh-v1.5"


def chunk_models_dir(models_home: Path) -> Path:
    return models_home / "chunk"


def model_dir(models_home: Path, model_id: str) -> Path:
    meta = CATALOG[model_id]
    return chunk_models_dir(models_home) / meta.get("local_name", model_id)


def model_ready(models_home: Path, model_id: str) -> bool:
    if model_id not in CATALOG:
        return False
    d = model_dir(models_home, model_id)
    if not d.is_dir():
        return False
    return (d / "config.json").is_file() or any(d.glob("*.bin")) or any(d.glob("*.safetensors"))
