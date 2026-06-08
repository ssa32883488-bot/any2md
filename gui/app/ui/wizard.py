"""First-run setup wizard (tkinter)."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from typing import Callable

from app.config import load_config, save_config
from app.download_worker import DownloadWorker, WorkerEvent
from app.gpu_probe import GpuInfo, probe_gpu
from app.model_catalog import MODELS, total_size_mb
from app.paths import app_root, default_models_dir
from app.ui.chunk_dialog import open_chunk_download_dialog


def _forbid_c_drive(path: Path) -> bool:
    return path.drive.upper() == "C:"


class WizardApp(tk.Tk):
    def __init__(self, on_complete: callable | None = None) -> None:
        super().__init__()
        self._on_complete = on_complete
        self.title("any2md 首次设置")
        self.geometry("720x520")
        self.minsize(640, 460)
        self.resizable(True, True)

        self._gpu_info: GpuInfo | None = None
        self._models_dir = tk.StringVar(value=str(default_models_dir()))
        self._model_vars: dict[str, tk.BooleanVar] = {
            m.id: tk.BooleanVar(value=True) for m in MODELS
        }
        self._progress_var = tk.DoubleVar(value=0.0)
        self._status_var = tk.StringVar(value="就绪")
        self._worker: DownloadWorker | None = None

        self._container = ttk.Frame(self, padding=16)
        self._container.pack(fill=tk.BOTH, expand=True)
        self._frames: dict[str, ttk.Frame] = {}
        self._build_frames()
        self.show("welcome")

    def _clear_container(self) -> None:
        for w in self._container.winfo_children():
            w.destroy()

    def _page(self, name: str, builder: Callable[[ttk.Frame], None]) -> None:
        frame = ttk.Frame(self._container)
        self._frames[name] = frame
        builder(frame)

    def _build_frames(self) -> None:
        self._page("welcome", self._build_welcome)
        self._page("gpu_running", self._build_gpu_running)
        self._page("gpu_result", self._build_gpu_result)
        self._page("model_confirm", self._build_model_confirm)
        self._page("model_setup", self._build_model_setup)
        self._page("downloading", self._build_downloading)
        self._page("finish", self._build_finish)

    def show(self, name: str) -> None:
        for f in self._frames.values():
            f.pack_forget()
        self._frames[name].pack(fill=tk.BOTH, expand=True)

    # --- pages ---

    def _build_welcome(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="欢迎使用 any2md", font=("Segoe UI", 16, "bold")).pack(
            anchor=tk.W, pady=(0, 8)
        )
        ttk.Label(
            parent,
            text="本程序需要 NVIDIA 显卡才能运行文档解析。",
            wraplength=640,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 24))

        ttk.Label(parent, text="是否启用显卡自动检测？", font=("Segoe UI", 11, "bold")).pack(
            anchor=tk.W, pady=(0, 12)
        )

        btns = ttk.Frame(parent)
        btns.pack(anchor=tk.W)
        ttk.Button(btns, text="是，开始检测", command=self._start_gpu_check).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(btns, text="否，退出程序", command=self.destroy).pack(side=tk.LEFT)

    def _build_gpu_running(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="正在检测显卡…", font=("Segoe UI", 14, "bold")).pack(
            anchor=tk.W, pady=(0, 12)
        )
        self._gpu_log = tk.Text(parent, height=12, wrap=tk.WORD, state=tk.DISABLED)
        self._gpu_log.pack(fill=tk.BOTH, expand=True)
        self._gpu_progress = ttk.Progressbar(parent, mode="indeterminate")
        self._gpu_progress.pack(fill=tk.X, pady=12)

    def _build_gpu_result(self, parent: ttk.Frame) -> None:
        self._gpu_result_title = ttk.Label(parent, font=("Segoe UI", 14, "bold"))
        self._gpu_result_title.pack(anchor=tk.W, pady=(0, 8))
        self._gpu_result_body = ttk.Label(parent, wraplength=640, justify=tk.LEFT)
        self._gpu_result_body.pack(anchor=tk.W, pady=(0, 16))
        self._gpu_result_btns = ttk.Frame(parent)
        self._gpu_result_btns.pack(anchor=tk.W)

    def _build_model_setup(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="下载模型", font=("Segoe UI", 14, "bold")).pack(
            anchor=tk.W, pady=(0, 8)
        )
        ttk.Label(
            parent,
            text="请选择要下载的模型与保存目录（默认与程序同盘，不建议跨盘或 C 盘）。",
            wraplength=640,
        ).pack(anchor=tk.W, pady=(0, 12))

        dir_row = ttk.Frame(parent)
        dir_row.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(dir_row, text="目录：").pack(side=tk.LEFT)
        ttk.Entry(dir_row, textvariable=self._models_dir).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=6
        )
        ttk.Button(dir_row, text="浏览…", command=self._pick_models_dir).pack(side=tk.LEFT)

        ttk.Label(parent, text="模型列表：", font=("Segoe UI", 10, "bold")).pack(
            anchor=tk.W
        )
        for m in MODELS:
            row = ttk.Frame(parent)
            row.pack(fill=tk.X, pady=4)
            ttk.Checkbutton(
                row,
                text=f"{m.label}（约 {m.size_mb} MB）",
                variable=self._model_vars[m.id],
            ).pack(anchor=tk.W)
            ttk.Label(row, text=f"  {m.description}", foreground="#555").pack(anchor=tk.W)

        self._size_label = ttk.Label(parent, text="")
        self._size_label.pack(anchor=tk.W, pady=8)
        self._update_size_label()

        for var in self._model_vars.values():
            var.trace_add("write", lambda *_: self._update_size_label())

        btns = ttk.Frame(parent)
        btns.pack(anchor=tk.W, pady=(16, 0))
        ttk.Button(btns, text="开始下载", command=self._start_download).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(btns, text="跳过并退出", command=self.destroy).pack(side=tk.LEFT)

    def _build_downloading(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="正在下载模型…", font=("Segoe UI", 14, "bold")).pack(
            anchor=tk.W, pady=(0, 8)
        )
        ttk.Label(parent, textvariable=self._status_var).pack(anchor=tk.W, pady=(0, 8))
        ttk.Progressbar(
            parent, variable=self._progress_var, maximum=100, mode="determinate"
        ).pack(fill=tk.X, pady=(0, 12))
        self._dl_log = tk.Text(parent, height=16, wrap=tk.WORD, state=tk.DISABLED)
        scroll = ttk.Scrollbar(parent, command=self._dl_log.yview)
        self._dl_log.configure(yscrollcommand=scroll.set)
        self._dl_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_finish(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="设置完成", font=("Segoe UI", 16, "bold")).pack(
            anchor=tk.W, pady=(0, 12)
        )
        ttk.Label(
            parent,
            text="OCR 模型已就绪。点击下面按钮进入主界面，开始转换文档。",
            wraplength=640,
        ).pack(anchor=tk.W, pady=(0, 8))
        ttk.Label(
            parent,
            text="可选：如需 RAG 知识库语义切分，可下载 BGE-base 模型（约 400MB，魔搭 ModelScope，国内 CDN）。",
            wraplength=640,
            foreground="#555",
        ).pack(anchor=tk.W, pady=(0, 16))
        btns = ttk.Frame(parent)
        btns.pack(anchor=tk.W)
        ttk.Button(
            btns,
            text="下载语义切分模型（可选）",
            command=self._download_chunk_model,
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btns, text="进入主界面", command=self._finish_wizard).pack(side=tk.LEFT)

    # --- actions ---

    def _append_log(self, widget: tk.Text, line: str) -> None:
        widget.configure(state=tk.NORMAL)
        widget.insert(tk.END, line + "\n")
        widget.see(tk.END)
        widget.configure(state=tk.DISABLED)

    def _start_gpu_check(self) -> None:
        self.show("gpu_running")
        self._gpu_progress.start(12)
        self.after(80, self._run_gpu_check)

    def _run_gpu_check(self) -> None:
        self._append_log(self._gpu_log, "调用 nvidia-smi / WMI 检测 NVIDIA 显卡…")
        info = probe_gpu()
        self._gpu_info = info
        if info.name:
            self._append_log(self._gpu_log, f"显卡：{info.name}")
        if info.vram_mb:
            self._append_log(self._gpu_log, f"显存：{info.vram_mb} MB")
        if info.driver:
            self._append_log(self._gpu_log, f"驱动：{info.driver}")
        self._append_log(self._gpu_log, f"结论：{info.reason}")
        self._gpu_progress.stop()
        self.after(400, self._show_gpu_result)

    def _show_gpu_result(self) -> None:
        info = self._gpu_info
        if not info:
            return

        for w in self._gpu_result_btns.winfo_children():
            w.destroy()

        if info.ok:
            self._gpu_result_title.configure(text="显卡检测通过")
            body = f"{info.name}\n{info.reason}"
            if info.vram_mb:
                body += f"\n显存：{info.vram_mb} MB"
            self._gpu_result_body.configure(text=body)
            ttk.Button(
                self._gpu_result_btns,
                text="继续",
                command=lambda: self.show("model_confirm"),
            ).pack(side=tk.LEFT)
        else:
            self._gpu_result_title.configure(text="本机不建议使用 any2md")
            self._gpu_result_body.configure(
                text=f"{info.reason}\n\n需要 NVIDIA GPU（建议 6GB+ 显存）与 paddlepaddle-gpu。"
            )
            ttk.Button(
                self._gpu_result_btns,
                text="确认并退出",
                command=self.destroy,
            ).pack(side=tk.LEFT)

        self.show("gpu_result")

    def _build_model_confirm(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="下载模型", font=("Segoe UI", 14, "bold")).pack(
            anchor=tk.W, pady=(0, 8)
        )
        ttk.Label(
            parent,
            text=(
                "首次使用需要下载约 2 GB 模型文件（国内 BOS 镜像，无需 VPN）。\n"
                "是否现在下载？"
            ),
            wraplength=640,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 24))
        btns = ttk.Frame(parent)
        btns.pack(anchor=tk.W)
        ttk.Button(btns, text="是，选择目录并下载", command=lambda: self.show("model_setup")).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(btns, text="否，退出程序", command=self.destroy).pack(side=tk.LEFT)

    def _pick_models_dir(self) -> None:
        initial = self._models_dir.get() or str(app_root())
        chosen = filedialog.askdirectory(initialdir=initial, title="选择模型下载目录")
        if chosen:
            self._models_dir.set(chosen)

    def _selected_models(self) -> list[str]:
        return [mid for mid, var in self._model_vars.items() if var.get()]

    def _update_size_label(self) -> None:
        ids = self._selected_models()
        mb = total_size_mb(ids)
        self._size_label.configure(
            text=f"合计约 {mb} MB（国内 BOS 镜像，无需 VPN）" if ids else "请至少选择一个模型"
        )

    def _start_download(self) -> None:
        try:
            ids = self._selected_models()
            if not ids:
                messagebox.showwarning("提示", "请至少选择一个模型")
                return

            path = Path(self._models_dir.get()).expanduser().resolve()
            if _forbid_c_drive(path):
                messagebox.showerror("错误", "模型目录不能设在 C 盘，请选择其他盘符。")
                return

            app_drive = app_root().drive.upper()
            if path.drive.upper() != app_drive:
                if not messagebox.askyesno(
                    "跨盘提示",
                    f"程序在 {app_drive}，模型目录在 {path.drive}，跨盘可能影响性能。\n是否继续？",
                ):
                    return

            # 先切到下载页，避免用户以为没反应
            self._progress_var.set(0)
            self._status_var.set("准备下载…")
            self.show("downloading")
            self.update_idletasks()

            path.mkdir(parents=True, exist_ok=True)
            save_config(
                {
                    **load_config(),
                    "models_dir": str(path),
                    "models": ids,
                    "setup_complete": False,
                }
            )

            self._worker = DownloadWorker(path, ids, self._on_download_event)
            self._worker.start()
        except Exception as exc:
            messagebox.showerror("无法开始下载", str(exc))
            self.show("model_setup")

    def _on_download_event(self, ev: WorkerEvent) -> None:
        def apply() -> None:
            if ev.kind == "log":
                self._append_log(self._dl_log, ev.message)
                self._status_var.set(ev.message[:80])
            elif ev.kind == "progress" and ev.percent is not None:
                self._progress_var.set(ev.percent)
                self._status_var.set(ev.message)
                # 日志按阶段节流，避免高频刷新拖慢下载线程
                stage = (ev.extra or {}).get("stage", "")
                if stage in ("init", "start", "complete", "skip", "done") or ev.percent >= 99:
                    self._append_log(self._dl_log, ev.message)
            elif ev.kind == "done":
                self._progress_var.set(100)
                save_config(
                    {
                        "models_dir": self._models_dir.get(),
                        "models": self._selected_models(),
                        "setup_complete": True,
                    }
                )
                self.show("finish")
            elif ev.kind == "error":
                messagebox.showerror("下载失败", ev.message)
                self._append_log(self._dl_log, f"[错误] {ev.message}")
                self.show("model_setup")

        self.after(0, apply)

    def _finish_wizard(self) -> None:
        cb = self._on_complete
        self.destroy()
        if cb:
            cb()

    def _download_chunk_model(self) -> None:
        open_chunk_download_dialog(self)


def run_wizard(on_complete: callable | None = None) -> None:
    app = WizardApp(on_complete=on_complete)
    app.mainloop()
