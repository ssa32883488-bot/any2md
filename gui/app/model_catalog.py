"""Fixed model catalog for the setup wizard."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelItem:
    id: str
    label: str
    description: str
    size_mb: int
    required: bool = True


MODELS: tuple[ModelItem, ...] = (
    ModelItem(
        id="PP-DocLayoutV3",
        label="版面分析模型",
        description="检测标题、段落、表格、图片等区域（PP-DocLayoutV3）",
        size_mb=126,
        required=True,
    ),
    ModelItem(
        id="PaddleOCR-VL-1.6",
        label="文档语义 / VLM 模型",
        description="扫描件 OCR + 结构化 Markdown（PaddleOCR-VL v1.6）",
        size_mb=1840,
        required=True,
    ),
)


def total_size_mb(model_ids: list[str]) -> int:
    lookup = {m.id: m for m in MODELS}
    return sum(lookup[mid].size_mb for mid in model_ids if mid in lookup)
