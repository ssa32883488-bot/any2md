"""Dialogs for chunk model download."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from app.chunk_catalog import CHUNK_MODELS, DEFAULT_CHUNK_MODEL
from app.chunk_download_worker import ChunkDownloadEvent, ChunkDownloadWorker
from app.config import get_models_dir


class ChunkDownloadDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, *, model_id: str | None = None) -> None:
        super().__init__(master)
        self.title("下载语义切分模型")
        self.geometry("520x420")
        self.transient(master)
        self.grab_set()

        self._model_id = tk.StringVar(value=model_id or DEFAULT_CHUNK_MODEL)
        self._progress = tk.DoubleVar(value=0.0)
        self._status = tk.StringVar(value="就绪")
        self._worker: ChunkDownloadWorker | None = None

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text="语义切分用于 RAG 知识库，将 Markdown 切成适合检索的小块。",
            wraplength=480,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 12))

        row = ttk.Frame(frame)
        row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(row, text="模型").pack(side=tk.LEFT)
        ttk.Combobox(
            row,
            textvariable=self._model_id,
            values=[m.id for m in CHUNK_MODELS],
            state="readonly",
            width=32,
        ).pack(side=tk.LEFT, padx=8)

        for m in CHUNK_MODELS:
            ttk.Label(frame, text=f"· {m.label}：{m.description}（约 {m.size_mb} MB）", foreground="#555").pack(
                anchor=tk.W
            )

        ttk.Label(frame, textvariable=self._status).pack(anchor=tk.W, pady=(12, 4))
        ttk.Progressbar(frame, variable=self._progress, maximum=100).pack(fill=tk.X, pady=(0, 8))

        btns = ttk.Frame(frame)
        btns.pack(fill=tk.X, pady=(0, 8))
        self._start_btn = ttk.Button(btns, text="开始下载", command=self._start)
        self._start_btn.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btns, text="关闭", command=self.destroy).pack(side=tk.LEFT)

        self._log = tk.Text(frame, height=6, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9))
        self._log.pack(fill=tk.BOTH, expand=True)

    def _append(self, line: str) -> None:
        self._log.configure(state=tk.NORMAL)
        self._log.insert(tk.END, line + "\n")
        self._log.see(tk.END)
        self._log.configure(state=tk.DISABLED)

    def _start(self) -> None:
        mid = self._model_id.get()
        self._start_btn.configure(state=tk.DISABLED)
        self._progress.set(0)
        self._status.set("准备下载…")
        self._worker = ChunkDownloadWorker(
            get_models_dir(),
            [mid],
            self._on_event,
        )
        self._worker.start()

    def _on_event(self, ev: ChunkDownloadEvent) -> None:
        def apply() -> None:
            if ev.kind == "log":
                self._append(ev.message)
            elif ev.kind == "progress" and ev.percent is not None:
                self._progress.set(ev.percent)
                self._status.set(ev.message)
            elif ev.kind == "done":
                self._progress.set(100)
                self._status.set(ev.message)
                self._start_btn.configure(state=tk.NORMAL)
                messagebox.showinfo("完成", ev.message, parent=self)
            elif ev.kind == "error":
                self._status.set("失败")
                self._start_btn.configure(state=tk.NORMAL)
                messagebox.showerror("下载失败", ev.message, parent=self)

        self.after(0, apply)


def open_chunk_download_dialog(master: tk.Misc, *, model_id: str | None = None) -> None:
    ChunkDownloadDialog(master, model_id=model_id)
