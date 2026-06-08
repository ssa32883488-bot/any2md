"""Download models in-process (no external Python required)."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.model_downloader import download_models
from app.paths import app_root


@dataclass
class WorkerEvent:
    kind: str  # log | progress | done | error
    message: str
    percent: float | None = None
    extra: dict | None = None


class DownloadWorker:
    def __init__(
        self,
        models_dir: Path,
        model_ids: list[str],
        on_event: Callable[[WorkerEvent], None],
    ) -> None:
        self.models_dir = models_dir.resolve()
        self.model_ids = model_ids
        self.on_event = on_event
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        self.on_event(WorkerEvent("log", f"程序目录：{app_root()}"))
        self.on_event(WorkerEvent("log", f"保存到：{self.models_dir}"))
        self.on_event(WorkerEvent("progress", "连接国内镜像…", percent=0.0))

        def on_progress(stage: str, message: str, percent: float | None) -> None:
            if stage == "error":
                self.on_event(WorkerEvent("error", message))
            elif stage == "done":
                self.on_event(WorkerEvent("done", message, percent=100.0))
            elif stage in ("download", "start", "complete", "progress", "init", "skip"):
                kind = "progress" if percent is not None else "log"
                self.on_event(
                    WorkerEvent(kind, message, percent=percent, extra={"stage": stage})
                )
            else:
                self.on_event(WorkerEvent("log", message))

        try:
            download_models(self.models_dir, self.model_ids, on_progress)
        except Exception as exc:
            self.on_event(WorkerEvent("error", str(exc)))
