"""Run engine/run_chunker.py for Markdown semantic chunking."""

from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.config import get_models_dir
from app.paths import app_root, engine_dir, find_python, isolated_env, python_not_found_message


@dataclass
class ChunkEvent:
    kind: str  # log | progress | done | error
    message: str
    percent: float | None = None
    extra: dict | None = None


class ChunkWorker:
    def __init__(
        self,
        md_paths: list[Path],
        *,
        chunk_model: str = "bge-base-zh-v1.5",
        chunk_mode: str = "auto",
        on_event: Callable[[ChunkEvent], None],
    ) -> None:
        self.md_paths = [p.resolve() for p in md_paths]
        self.chunk_model = chunk_model
        self.chunk_mode = chunk_mode
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
            self.on_event(ChunkEvent("error", python_not_found_message()))
            return

        script = engine_dir() / "run_chunker.py"
        if not script.is_file():
            self.on_event(ChunkEvent("error", f"切分脚本不存在：{script}"))
            return

        models_dir = get_models_dir()
        total = len(self.md_paths)

        for idx, md in enumerate(self.md_paths, start=1):
            self.on_event(
                ChunkEvent(
                    "progress",
                    f"切分 ({idx}/{total})：{md.name}",
                    percent=(idx - 1) / total * 100.0,
                )
            )
            cmd = [
                str(python),
                str(script),
                "-i",
                str(md),
                "--models-dir",
                str(models_dir),
                "--chunk-model",
                self.chunk_model,
                "--mode",
                self.chunk_mode,
            ]
            env = isolated_env(
                {"ANY2MD_MODELS_DIR": str(models_dir), "ANY2MD_APP_ROOT": str(app_root())}
            )
            try:
                proc = subprocess.Popen(
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
                self.on_event(ChunkEvent("error", str(exc)))
                return

            self._proc = proc
            assert proc.stderr is not None
            json_path = ""
            for line in proc.stderr:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("[") and not line.startswith("{"):
                    self.on_event(ChunkEvent("log", line))
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    self.on_event(ChunkEvent("log", line))
                    continue
                stage = data.get("stage", "")
                msg = data.get("message", "")
                if stage == "error":
                    self.on_event(ChunkEvent("error", msg, extra=data))
                    return
                if stage == "chunk":
                    self.on_event(ChunkEvent("progress", msg, percent=idx / total * 90.0, extra=data))
                    self.on_event(ChunkEvent("log", msg))
                elif stage == "done":
                    json_path = data.get("chunks_json", "")
                    self.on_event(ChunkEvent("log", msg))
                elif stage == "init":
                    self.on_event(ChunkEvent("log", msg))

            proc.wait()
            if proc.returncode != 0:
                self.on_event(ChunkEvent("error", f"切分失败：{md.name}，退出码 {proc.returncode}"))
                return

        self.on_event(
            ChunkEvent(
                "done",
                f"切分完成，共 {total} 个文件",
                percent=100.0,
                extra={"count": total},
            )
        )
