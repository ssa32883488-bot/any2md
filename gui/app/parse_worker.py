"""Run engine/run_parser.py in background with live JSON logs."""

from __future__ import annotations

import json
import re
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.config import get_models_dir
from app.file_types import needs_paddle
from app.paths import app_root, engine_dir, find_python, isolated_env, python_not_found_message

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_SKIP_LOG = (
    "UserWarning:",
    "Warning:",
    "warnings.warn",
    "paddle\\tensor",
    "paddle\\utils\\decorator",
    "Non compatible API",
)


@dataclass
class ParseEvent:
    kind: str  # log | progress | done | error | batch
    message: str
    percent: float | None = None
    stage: str | None = None
    extra: dict | None = None


def _should_skip_log(line: str) -> bool:
    if _ANSI.search(line):
        line = _ANSI.sub("", line)
    return any(s in line for s in _SKIP_LOG)


class ParseWorker:
    def __init__(
        self,
        input_path: Path,
        output_dir: Path,
        *,
        use_unwarping: bool = False,
        use_orientation: bool = False,
        parse_mode: str = "auto",
        chunk_model: str = "none",
        on_event: Callable[[ParseEvent], None],
    ) -> None:
        self.input_path = input_path.resolve()
        self.output_dir = output_dir.resolve()
        self.use_unwarping = use_unwarping
        self.use_orientation = use_orientation
        self.parse_mode = parse_mode
        self.chunk_model = chunk_model
        self.on_event = on_event
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._got_done = False

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    def _run(self) -> None:
        require_paddle = needs_paddle(self.input_path, self.parse_mode)
        python = find_python(require_paddle=require_paddle)
        if not python:
            self.on_event(ParseEvent("error", python_not_found_message()))
            return

        script = engine_dir() / "run_parser.py"
        if not script.is_file():
            self.on_event(ParseEvent("error", f"引擎脚本不存在：{script}"))
            return

        models_dir = get_models_dir()
        cmd = [
            str(python),
            str(script),
            "-i",
            str(self.input_path),
            "-o",
            str(self.output_dir),
            "--models-dir",
            str(models_dir),
            "--route",
            self.parse_mode,
            "--chunk-model",
            self.chunk_model,
        ]
        if self.use_unwarping:
            cmd.append("--use-unwarping")
        if self.use_orientation:
            cmd.append("--use-orientation")

        env = isolated_env(
            {
                "ANY2MD_MODELS_DIR": str(models_dir),
                "ANY2MD_APP_ROOT": str(app_root()),
            }
        )

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.on_event(ParseEvent("log", f"Python：{python}"))
        self.on_event(ParseEvent("log", f"程序目录：{app_root()}"))
        self.on_event(ParseEvent("log", f"输入：{self.input_path.name}"))
        self.on_event(ParseEvent("log", f"输出：{self.output_dir}"))
        self.on_event(ParseEvent("log", f"解析模式：{self.parse_mode}，语义切分：{self.chunk_model}"))
        if require_paddle:
            self.on_event(ParseEvent("log", f"OCR 模型：{models_dir}"))
        self.on_event(
            ParseEvent("progress", "正在启动引擎…", percent=2.0, stage="init", extra={})
        )

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
            self.on_event(ParseEvent("error", str(exc)))
            return

        assert self._proc.stderr is not None
        total_pages: int | None = None

        for line in self._proc.stderr:
            line = line.strip()
            if not line:
                continue

            if line.startswith("[") and "]" in line and not line.startswith("{"):
                if not _should_skip_log(line):
                    self.on_event(ParseEvent("log", line))
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                if line and not _should_skip_log(line):
                    self.on_event(ParseEvent("log", line))
                continue

            stage = data.get("stage", "")
            msg = data.get("message", "")

            if stage == "error":
                self.on_event(ParseEvent("error", msg, extra=data))
                return

            if "total_pages" in data and data["total_pages"]:
                total_pages = int(data["total_pages"])

            if stage == "route":
                self.on_event(ParseEvent("log", msg, stage=stage, extra=data))
            elif stage == "init":
                ready = "就绪" in msg
                self.on_event(
                    ParseEvent(
                        "progress",
                        msg,
                        percent=12.0 if ready else 6.0,
                        stage=stage,
                        extra=data,
                    )
                )
            elif stage == "models":
                self.on_event(
                    ParseEvent("progress", msg, percent=4.0, stage=stage, extra=data)
                )
            elif stage == "predict":
                page = int(data.get("page") or 0)
                tp = int(data.get("total_pages") or total_pages or 0) or None
                extra = {**data, "total_pages": tp, "page": page}
                if "开始" in msg and tp:
                    self.on_event(
                        ParseEvent(
                            "progress",
                            f"共 {tp} 页，开始处理…",
                            percent=15.0,
                            stage=stage,
                            extra=extra,
                        )
                    )
                elif page:
                    pct = 15.0 + (page / tp * 70.0 if tp else page * 8.0)
                    self.on_event(
                        ParseEvent(
                            "progress",
                            msg,
                            percent=min(88.0, pct),
                            stage=stage,
                            extra=extra,
                        )
                    )
                else:
                    self.on_event(
                        ParseEvent("progress", msg, percent=18.0, stage=stage, extra=extra)
                    )
            elif stage == "chunk":
                self.on_event(
                    ParseEvent("progress", msg, percent=95.0, stage=stage, extra=data)
                )
                self.on_event(ParseEvent("log", f"[chunk] {msg}"))
            elif stage in ("restructure", "save"):
                self.on_event(
                    ParseEvent("progress", msg, percent=93.0, stage=stage, extra=data)
                )
            elif stage == "done":
                self._got_done = True
                self.on_event(
                    ParseEvent("done", msg, percent=100.0, stage=stage, extra=data)
                )
            elif stage != "error":
                self.on_event(ParseEvent("log", msg, stage=stage, extra=data))

        if self._proc.stdout:
            self._proc.stdout.read()
        code = self._proc.wait()

        md_dir = self.output_dir / "md"
        if md_dir.is_dir():
            md_files = sorted(md_dir.glob("*.md"))
        else:
            md_files = sorted(self.output_dir.rglob("*.md"))
            md_files = [p for p in md_files if p.parent.name != "chunks"]
        if code != 0:
            hint = ""
            if code == 9009:
                hint = (
                    "\n\n系统找到了 Windows 应用商店的 Python 占位程序，无法运行引擎。\n"
                    "请在「设置 → 选择 Python 解释器…」指定真实 python.exe\n"
                    f"（例如 F:\\Python\\Python 3.13.0\\python.exe）。"
                )
            elif code == 3221225477 or code == -1073741819:
                hint = (
                    "\n\nGPU 引擎崩溃（0xC0000005）。可尝试：\n"
                    "1. 解析模式选「仅文本提取」或「自动」\n"
                    "2. 关闭其他占显存的程序后重试"
                )
            self.on_event(ParseEvent("error", f"转换失败，退出码 {code}{hint}"))
        elif not md_files:
            self.on_event(
                ParseEvent(
                    "error",
                    f"未生成 Markdown 文件。\n输出目录：{self.output_dir}\n"
                    "请确认模型已下载到本程序 models 目录后重试。",
                )
            )
        elif not self._got_done:
            self.on_event(
                ParseEvent(
                    "done",
                    "转换完成",
                    percent=100.0,
                    extra={"markdown_files": [str(p) for p in md_files], "output_dir": str(self.output_dir)},
                )
            )
