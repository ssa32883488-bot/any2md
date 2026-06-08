"""Download chunk embedding models via engine/download_chunk_models.py."""

from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.paths import app_root, engine_dir, find_python, isolated_env


@dataclass
class ChunkDownloadEvent:
    kind: str  # log | progress | done | error
    message: str
    percent: float | None = None


class ChunkDownloadWorker:
    def __init__(
        self,
        models_dir: Path,
        model_ids: list[str],
        on_event: Callable[[ChunkDownloadEvent], None],
    ) -> None:
        self.models_dir = models_dir.resolve()
        self.model_ids = model_ids
        self.on_event = on_event
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    def _run(self) -> None:
        python = find_python(require_paddle=False)
        if not python:
            self.on_event(
                ChunkDownloadEvent(
                    "error",
                    "未找到 Python。请安装 Python 并执行：pip install modelscope",
                )
            )
            return

        script = engine_dir() / "download_chunk_models.py"
        if not script.is_file():
            self.on_event(ChunkDownloadEvent("error", f"脚本不存在：{script}"))
            return

        cmd = [
            str(python),
            str(script),
            "--models-dir",
            str(self.models_dir),
            *sum([["--models", mid] for mid in self.model_ids], []),
        ]
        env = isolated_env({"ANY2MD_MODELS_DIR": str(self.models_dir), "ANY2MD_APP_ROOT": str(app_root())})
        self.on_event(ChunkDownloadEvent("log", f"下载到：{self.models_dir / 'chunk'}"))
        self.on_event(ChunkDownloadEvent("progress", "连接魔搭 ModelScope…", percent=5.0))

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                cwd=str(app_root()),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            self.on_event(ChunkDownloadEvent("error", str(exc)))
            return

        assert self._proc.stderr is not None
        total = len(self.model_ids)
        done_n = 0
        for line in self._proc.stderr:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                self.on_event(ChunkDownloadEvent("log", line))
                continue
            stage = data.get("stage", "")
            msg = data.get("message", "")
            if stage == "error":
                self.on_event(ChunkDownloadEvent("error", msg))
                return
            if stage in ("start", "complete", "skip"):
                if stage == "complete":
                    done_n += 1
                pct = min(95.0, done_n / max(total, 1) * 100.0)
                self.on_event(ChunkDownloadEvent("progress", msg, percent=pct))
                self.on_event(ChunkDownloadEvent("log", msg))
            elif stage == "done":
                self.on_event(ChunkDownloadEvent("done", msg, percent=100.0))
                return

        code = self._proc.wait()
        if code != 0:
            self.on_event(ChunkDownloadEvent("error", f"下载失败，退出码 {code}"))
        else:
            self.on_event(ChunkDownloadEvent("done", "切分模型下载完成", percent=100.0))
