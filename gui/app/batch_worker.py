"""Sequential batch conversion into one timestamped output folder."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from app.parse_worker import ParseEvent, ParseWorker


class BatchParseWorker:
    def __init__(
        self,
        files: list[Path],
        batch_root: Path,
        *,
        use_unwarping: bool = False,
        use_orientation: bool = False,
        parse_mode: str = "auto",
        chunk_model: str = "none",
        on_event: Callable[[ParseEvent], None],
    ) -> None:
        self.files = files
        self.batch_root = batch_root.resolve()
        self.use_unwarping = use_unwarping
        self.use_orientation = use_orientation
        self.parse_mode = parse_mode
        self.chunk_model = chunk_model
        self.on_event = on_event
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._current: ParseWorker | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()
        if self._current:
            self._current.cancel()

    def _run(self) -> None:
        total = len(self.files)
        all_md: list[str] = []

        for idx, path in enumerate(self.files, start=1):
            if self._cancel.is_set():
                return

            done = threading.Event()
            error_msg: list[str] = []

            def wrap(ev: ParseEvent, *, file_index=idx, file_total=total, file_path=path) -> None:
                extra = dict(ev.extra or {})
                extra["batch_index"] = file_index
                extra["batch_total"] = file_total
                extra["batch_file"] = file_path.name
                extra["batch_root"] = str(self.batch_root)
                if ev.kind == "done":
                    md = extra.get("markdown_files") or []
                    all_md.extend(md)
                    self.on_event(
                        ParseEvent(
                            "log",
                            f"完成 ({file_index}/{file_total})：{file_path.name}",
                            extra=extra,
                        )
                    )
                    done.set()
                    return
                if ev.kind == "error":
                    error_msg.append(ev.message)
                    self.on_event(ParseEvent("error", ev.message, extra=extra))
                    done.set()
                    return
                wrapped = ParseEvent(
                    ev.kind,
                    ev.message,
                    percent=ev.percent,
                    stage=ev.stage,
                    extra=extra,
                )
                self.on_event(wrapped)

            self.on_event(
                ParseEvent(
                    "batch",
                    f"开始处理 ({idx}/{total})：{path.name}",
                    stage="batch",
                    extra={
                        "batch_index": idx,
                        "batch_total": total,
                        "batch_file": path.name,
                        "batch_root": str(self.batch_root),
                    },
                )
            )

            self._current = ParseWorker(
                path.resolve(),
                self.batch_root,
                use_unwarping=self.use_unwarping,
                use_orientation=self.use_orientation,
                parse_mode=self.parse_mode,
                chunk_model=self.chunk_model,
                on_event=wrap,
            )
            self._current.start()
            done.wait()

            if error_msg:
                self.on_event(ParseEvent("error", error_msg[0]))
                return

        self.on_event(
            ParseEvent(
                "done",
                f"批量完成，共 {total} 个文件",
                percent=100.0,
                stage="done",
                extra={
                    "markdown_files": all_md,
                    "batch_total": total,
                    "batch_root": str(self.batch_root),
                    "output_dir": str(self.batch_root),
                },
            )
        )
