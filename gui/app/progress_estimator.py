"""Progress percent and ETA formatting for the GUI."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


def fmt_duration(seconds: float) -> str:
    if seconds < 0 or seconds != seconds:  # NaN
        return "—"
    s = int(seconds)
    if s < 60:
        return f"{s} 秒"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m} 分 {s} 秒"
    h, m = divmod(m, 60)
    return f"{h} 时 {m} 分"


@dataclass
class ProgressEstimator:
    """Map engine stages to 0–100% and estimate remaining time."""

    batch_index: int = 1
    batch_total: int = 1
    stage: str = "idle"
    page: int = 0
    total_pages: int | None = None
    percent: float = 0.0
    started_at: float = field(default_factory=time.monotonic)
    stage_started_at: float = field(default_factory=time.monotonic)
    page_times: list[float] = field(default_factory=list)
    init_hint_sec: float = 90.0
    per_page_hint_sec: float = 25.0

    def on_stage(self, stage: str, *, total_pages: int | None = None) -> None:
        self.stage = stage
        self.stage_started_at = time.monotonic()
        if total_pages is not None:
            self.total_pages = total_pages
        self._recalc()

    def on_page(self, page: int, *, total_pages: int | None = None) -> None:
        now = time.monotonic()
        if self.page > 0 and page > self.page:
            self.page_times.append(now - self.stage_started_at)
            if len(self.page_times) > 8:
                self.page_times.pop(0)
        self.page = page
        if total_pages is not None:
            self.total_pages = total_pages
        self.stage_started_at = now
        self._recalc()

    def on_batch(self, index: int, total: int) -> None:
        self.batch_index = index
        self.batch_total = total
        self._recalc()

    def _recalc(self) -> None:
        batch_slice = 100.0 / max(self.batch_total, 1)
        batch_base = (self.batch_index - 1) * batch_slice

        if self.stage in ("models", "init"):
            elapsed = time.monotonic() - self.stage_started_at
            inner = min(0.92, elapsed / max(self.init_hint_sec, 1.0))
            self.percent = batch_base + batch_slice * (0.02 + inner * 0.13)
        elif self.stage == "predict":
            tp = self.total_pages or max(self.page, 1)
            inner = min(0.88, self.page / tp if tp else 0.1)
            self.percent = batch_base + batch_slice * (0.15 + inner * 0.70)
        elif self.stage in ("restructure", "save"):
            self.percent = batch_base + batch_slice * 0.92
        elif self.stage == "chunk":
            elapsed = time.monotonic() - self.stage_started_at
            inner = min(0.90, elapsed / 60.0)
            self.percent = batch_base + batch_slice * (0.05 + inner * 0.85)
        elif self.stage == "done":
            self.percent = min(100.0, self.batch_index * batch_slice)
        else:
            self.percent = batch_base + batch_slice * 0.05

    def eta_seconds(self) -> float | None:
        elapsed = time.monotonic() - self.started_at
        if self.percent <= 1:
            return None
        if self.stage == "predict" and self.page > 0:
            tp = self.total_pages or self.page
            avg = (
                sum(self.page_times) / len(self.page_times)
                if self.page_times
                else self.per_page_hint_sec
            )
            remaining_pages = max(tp - self.page, 0)
            tail = 15.0  # restructure + save
            return remaining_pages * avg + tail
        if self.stage in ("models", "init"):
            return max(self.init_hint_sec - elapsed, 5.0)
        if self.percent > 2 and self.percent < 99:
            return elapsed * (100.0 - self.percent) / self.percent
        return None

    def status_line(self, detail: str = "") -> str:
        parts: list[str] = []
        if self.batch_total > 1:
            parts.append(f"文件 {self.batch_index}/{self.batch_total}")
        if self.stage == "init":
            parts.append("加载模型到 GPU")
        elif self.stage == "predict":
            if self.page and self.total_pages:
                parts.append(f"解析第 {self.page}/{self.total_pages} 页")
            elif self.page:
                parts.append(f"已完成 {self.page} 页")
            else:
                parts.append("正在解析")
        elif self.stage == "restructure":
            parts.append("合并跨页结构")
        elif self.stage == "save":
            parts.append("保存 Markdown")
        elif self.stage == "chunk":
            parts.append("语义切分")
        elif self.stage == "route":
            parts.append("选择解析路径")
        elif self.stage == "done":
            parts.append("完成")
        else:
            parts.append(detail or "处理中")

        eta = self.eta_seconds()
        if eta is not None and self.stage != "done":
            parts.append(f"预计剩余 {fmt_duration(eta)}")
        parts.append(f"已用 {fmt_duration(time.monotonic() - self.started_at)}")
        return " · ".join(parts)

    def pulse_suffix(self, tick: int) -> str:
        dots = "." * (1 + tick % 3)
        return dots
