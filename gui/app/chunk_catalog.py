"""Semantic chunking model catalog (mirrors engine/chunk_models.py)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_CHUNK_MODEL = "bge-base-zh-v1.5"


@dataclass(frozen=True)
class ChunkModelItem:
    id: str
    label: str
    description: str
    size_mb: int


CHUNK_MODELS: tuple[ChunkModelItem, ...] = (
    ChunkModelItem(
        id="bge-base-zh-v1.5",
        label="BGE-base-zh-v1.5",
        description="推荐默认，约 400MB，CPU 可跑，中文 RAG 够用",
        size_mb=400,
    ),
    ChunkModelItem(
        id="bge-large-zh-v1.5",
        label="BGE-large-zh-v1.5",
        description="更高质量，约 1.3GB",
        size_mb=1300,
    ),
    ChunkModelItem(
        id="gte-large-zh",
        label="GTE-large-zh",
        description="魔搭原生，约 650MB",
        size_mb=650,
    ),
)


def chunk_dir(models_home: Path, model_id: str) -> Path:
    return models_home / "chunk" / model_id


def chunk_model_ready(models_home: Path, model_id: str) -> bool:
    if model_id == "structure":
        return True
    d = chunk_dir(models_home, model_id)
    if not d.is_dir():
        return False
    return (
        (d / "config.json").is_file()
        or any(d.glob("*.bin"))
        or any(d.glob("*.safetensors"))
    )


def chunk_model_status(models_home: Path, model_id: str) -> tuple[bool, str]:
    if model_id == "none":
        return True, ""
    if chunk_model_ready(models_home, model_id):
        return True, str(chunk_dir(models_home, model_id))
    lookup = {m.id: m for m in CHUNK_MODELS}
    label = lookup.get(model_id, ChunkModelItem(model_id, model_id, "", 0)).label
    return False, (
        f"缺少语义切分模型：{label}\n"
        f"目录：{chunk_dir(models_home, model_id)}\n"
        "请在「设置 → 下载语义切分模型…」中下载（魔搭 ModelScope，国内 CDN）。"
    )
