"""Timestamped batch output: md/ json/ chunks/ assets/ with original file stems."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_SUBDIRS = ("md", "json", "chunks", "assets")


@dataclass(frozen=True)
class OutputBatch:
    root: Path

    @classmethod
    def create_under(cls, base: Path) -> OutputBatch:
        """Create a new batch folder under base, named by local time."""
        base = base.expanduser().resolve()
        base.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        root = base / ts
        for name in _SUBDIRS:
            (root / name).mkdir(parents=True, exist_ok=True)
        return cls(root)

    @classmethod
    def open(cls, root: Path) -> OutputBatch:
        root = root.expanduser().resolve()
        if not cls.is_batch_root(root):
            raise ValueError(f"不是有效的批次目录（缺少 md/ 等子目录）：{root}")
        return cls(root)

    @classmethod
    def resolve(cls, output: Path) -> OutputBatch:
        """Use existing batch root or create a new timestamped batch under output."""
        output = output.expanduser().resolve()
        if cls.is_batch_root(output):
            return cls.open(output)
        return cls.create_under(output)

    @staticmethod
    def is_batch_root(path: Path) -> bool:
        path = path.expanduser().resolve()
        return path.is_dir() and (path / "md").is_dir() and (path / "json").is_dir()

    @classmethod
    def from_md_path(cls, md_path: Path) -> OutputBatch | None:
        md_path = md_path.resolve()
        if md_path.parent.name == "md" and md_path.parent.parent.is_dir():
            root = md_path.parent.parent
            if cls.is_batch_root(root):
                return cls(root)
        return None

    def md_path(self, stem: str) -> Path:
        return self.root / "md" / f"{stem}.md"

    def chunks_json_path(self, stem: str) -> Path:
        return self.root / "json" / f"{stem}.chunks.json"

    def chunks_dir(self, stem: str) -> Path:
        return self.root / "chunks" / stem

    def assets_dir(self, stem: str) -> Path:
        return self.root / "assets" / stem

    def ocr_stage_dir(self, stem: str) -> Path:
        d = self.root / "assets" / "_ocr_stage" / stem
        d.mkdir(parents=True, exist_ok=True)
        return d

    def collect_ocr_outputs(self, stem: str, stage_dir: Path) -> list[Path]:
        """Move OCR markdown/json from staging into batch layout."""
        md_files = sorted(stage_dir.rglob("*.md"))
        json_files = sorted(stage_dir.rglob("*.json"))
        out_md: list[Path] = []

        if not md_files:
            return out_md

        if len(md_files) == 1:
            dest = self.md_path(stem)
            shutil.move(str(md_files[0]), dest)
            out_md.append(dest)
        else:
            for i, src in enumerate(md_files, start=1):
                name = stem if i == 1 else f"{stem}_{i:02d}"
                dest = self.md_path(name)
                shutil.move(str(src), dest)
                out_md.append(dest)

        for src in json_files:
            if src.name.endswith(".chunks.json"):
                stem = src.name[: -len(".chunks.json")]
                dest = self.chunks_json_path(stem)
            else:
                dest = self.root / "json" / src.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), dest)

        if stage_dir.exists():
            shutil.rmtree(stage_dir, ignore_errors=True)
        return out_md

    def summary(self) -> dict[str, str]:
        return {
            "batch_root": str(self.root),
            "md_dir": str(self.root / "md"),
            "json_dir": str(self.root / "json"),
            "chunks_dir": str(self.root / "chunks"),
            "assets_dir": str(self.root / "assets"),
        }
