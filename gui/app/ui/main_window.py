"""Main window: batch convert with ETA and live progress."""

from __future__ import annotations

import os
import shutil
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from typing import Callable

from app.batch_worker import BatchParseWorker
from app.config import get_models_dir, get_output_dir, load_config, models_ready, save_config, set_python_path
from app.chunk_catalog import DEFAULT_CHUNK_MODEL, chunk_model_status
from app.chunk_worker import ChunkEvent, ChunkWorker
from app.file_types import (
    CHUNK_MODEL_LABELS,
    FILE_DIALOG_PATTERN,
    PARSE_MODE_LABELS,
    SUPPORTED_EXTS,
    is_supported,
    needs_paddle,
)
from app.parse_worker import ParseEvent, ParseWorker
from app.output_layout import create_batch_dir
from app.paths import app_root, find_python
from app.progress_estimator import ProgressEstimator
from app.ui.chunk_dialog import open_chunk_download_dialog


_FILE_TYPES = (
    ("文档 / Office / 图片", FILE_DIALOG_PATTERN),
    ("PDF", "*.pdf"),
    ("Word", "*.docx;*.doc"),
    ("Excel", "*.xlsx;*.xls"),
    ("图片", "*.png;*.jpg;*.jpeg;*.bmp;*.tiff;*.webp;*.gif"),
    ("所有文件", "*.*"),
)


class MainWindow(tk.Tk):
    def __init__(self, *, on_open_setup: Callable[[], None] | None = None) -> None:
        super().__init__()
        self.title("any2md — 文档转 Markdown")
        self.geometry("820x620")
        self.minsize(720, 520)

        self._on_open_setup = on_open_setup
        self._output_dir = tk.StringVar(value=str(get_output_dir()))
        self._unwarp = tk.BooleanVar(value=False)
        self._orient = tk.BooleanVar(value=False)
        cfg = load_config()
        self._parse_mode = tk.StringVar(value=cfg.get("parse_mode", "auto"))
        self._chunk_model = tk.StringVar(value=cfg.get("chunk_model", "none"))
        self._semantic_chunk = tk.BooleanVar(value=cfg.get("chunk_model", "none") != "none")
        self._status = tk.StringVar(value="就绪 — 添加文件后点击「开始转换」")
        self._detail = tk.StringVar(value="")
        self._progress = tk.DoubleVar(value=0.0)
        self._worker: ParseWorker | BatchParseWorker | ChunkWorker | None = None
        self._busy = False
        self._last_md_files: list[str] = []
        self._actual_output_dir = get_output_dir()
        self._est = ProgressEstimator()
        self._tick = 0
        self._tick_job: str | None = None
        self._last_event_at = time.monotonic()

        self._build_menu()
        self._ensure_python()
        self._build_body()
        self._build_progress()
        self._build_actions()
        self._build_log()

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)
        settings = tk.Menu(menubar, tearoff=0)
        settings.add_command(label="下载语义切分模型…", command=self._download_chunk_model)
        settings.add_command(label="选择 Python 解释器…", command=self._pick_python)
        settings.add_command(label="重新运行首次设置…", command=self._open_setup)
        settings.add_command(label="打开模型目录", command=self._open_models_dir)
        settings.add_command(label="打开输出目录", command=self._open_output_dir)
        menubar.add_cascade(label="设置", menu=settings)
        tools = tk.Menu(menubar, tearoff=0)
        tools.add_command(label="仅切分 Markdown…", command=self._chunk_markdown_only)
        menubar.add_cascade(label="工具", menu=tools)
        self.config(menu=menubar)

    def _build_body(self) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill=tk.BOTH, expand=False)

        ttk.Label(
            frame,
            text="将 PDF / Word / Excel / 图片转为结构化 Markdown（智能路由 + 可选语义切分）",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor=tk.W, pady=(0, 8))

        list_frame = ttk.LabelFrame(frame, text="待转换文件", padding=8)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        inner = ttk.Frame(list_frame)
        inner.pack(fill=tk.BOTH, expand=True)
        self._file_list = tk.Listbox(inner, height=6, selectmode=tk.EXTENDED)
        scroll = ttk.Scrollbar(inner, command=self._file_list.yview)
        self._file_list.configure(yscrollcommand=scroll.set)
        self._file_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        btn_row = ttk.Frame(list_frame)
        btn_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(btn_row, text="添加文件…", command=self._add_files).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="添加文件夹…", command=self._add_folder).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="移除选中", command=self._remove_selected).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="清空", command=self._clear_files).pack(side=tk.LEFT)

        row = ttk.Frame(frame)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text="输出根目录").pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self._output_dir).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(row, text="浏览…", command=self._pick_output).pack(side=tk.LEFT)

        opts = ttk.Frame(frame)
        opts.pack(fill=tk.X, pady=(4, 0))
        ttk.Checkbutton(opts, text="扫描件弯曲矫正", variable=self._unwarp).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Checkbutton(opts, text="自动方向矫正", variable=self._orient).pack(side=tk.LEFT)
        ttk.Label(
            opts,
            text="（每次转换自动创建时间戳子文件夹：md / json / chunks / assets）",
            foreground="#666",
        ).pack(side=tk.LEFT, padx=(12, 0))

        route_row = ttk.Frame(frame)
        route_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(route_row, text="解析模式").pack(side=tk.LEFT)
        ttk.Combobox(
            route_row,
            textvariable=self._parse_mode,
            values=list(PARSE_MODE_LABELS.keys()),
            state="readonly",
            width=18,
        ).pack(side=tk.LEFT, padx=6)
        ttk.Label(
            route_row,
            text="（自动：可复制文字 PDF 走结构化 CPU 快路径，复杂版式失败则回退 OCR；扫描件走 OCR）",
            foreground="#666",
        ).pack(side=tk.LEFT)

        chunk_row = ttk.Frame(frame)
        chunk_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Checkbutton(
            chunk_row,
            text="启用语义切分",
            variable=self._semantic_chunk,
            command=self._on_semantic_toggle,
        ).pack(side=tk.LEFT)
        ttk.Label(chunk_row, text="模型").pack(side=tk.LEFT, padx=(12, 0))
        self._chunk_combo = ttk.Combobox(
            chunk_row,
            textvariable=self._chunk_model,
            values=[k for k in CHUNK_MODEL_LABELS if k != "none"],
            state="readonly" if self._semantic_chunk.get() else "disabled",
            width=28,
        )
        self._chunk_combo.pack(side=tk.LEFT, padx=6)
        if self._chunk_model.get() == "none":
            self._chunk_model.set("bge-base-zh-v1.5")
        self._on_semantic_toggle()

        ttk.Label(frame, text=f"模型：{get_models_dir()}", foreground="#666", wraplength=760).pack(
            anchor=tk.W, pady=(8, 0)
        )

    def _build_progress(self) -> None:
        mid = ttk.Frame(self, padding=(16, 4, 16, 0))
        mid.pack(fill=tk.X)
        ttk.Label(mid, textvariable=self._status, font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        ttk.Label(mid, textvariable=self._detail, foreground="#555").pack(anchor=tk.W, pady=(2, 4))
        self._pbar = ttk.Progressbar(mid, variable=self._progress, maximum=100, mode="determinate")
        self._pbar.pack(fill=tk.X)

    def _build_log(self) -> None:
        log_frame = ttk.LabelFrame(self, text="运行日志", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)
        self._log = tk.Text(log_frame, height=10, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9))
        scroll = ttk.Scrollbar(log_frame, command=self._log.yview)
        self._log.configure(yscrollcommand=scroll.set)
        self._log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_actions(self) -> None:
        bar = ttk.Frame(self, padding=(16, 8, 16, 0))
        bar.pack(fill=tk.X)
        self._convert_btn = ttk.Button(bar, text="开始转换", command=self._start_convert)
        self._convert_btn.pack(side=tk.LEFT, padx=(0, 8))
        self._cancel_btn = ttk.Button(bar, text="取消", command=self._cancel, state=tk.DISABLED)
        self._cancel_btn.pack(side=tk.LEFT, padx=(0, 8))
        self._chunk_btn = ttk.Button(bar, text="仅切分 Markdown", command=self._chunk_markdown_only)
        self._chunk_btn.pack(side=tk.LEFT, padx=(0, 8))
        self._open_btn = ttk.Button(
            bar, text="打开输出文件夹", command=self._open_output_dir, state=tk.DISABLED
        )
        self._open_btn.pack(side=tk.LEFT)

    def _files(self) -> list[Path]:
        return [Path(self._file_list.get(i)) for i in range(self._file_list.size())]

    def _download_chunk_model(self) -> None:
        if self._busy:
            messagebox.showwarning("提示", "任务进行中，请稍候")
            return
        open_chunk_download_dialog(self, model_id=self._chunk_model.get())

    def _chunk_markdown_only(self) -> None:
        if self._busy:
            messagebox.showwarning("提示", "任务进行中，请稍候")
            return
        paths = filedialog.askopenfilenames(
            title="选择 Markdown 文件",
            filetypes=[("Markdown", "*.md"), ("所有文件", "*.*")],
        )
        if not paths:
            return
        model_id = self._chunk_model.get() if self._semantic_chunk.get() else DEFAULT_CHUNK_MODEL
        ok, msg = chunk_model_status(get_models_dir(), model_id)
        if not ok:
            if messagebox.askyesno("缺少切分模型", f"{msg}\n\n是否现在下载？"):
                open_chunk_download_dialog(self, model_id=model_id)
            return
        out_base = Path(self._output_dir.get().strip()).expanduser().resolve()
        batch_root = create_batch_dir(out_base)
        staged: list[Path] = []
        for p in paths:
            src = Path(p).resolve()
            dest = batch_root / "md" / f"{src.stem}.md"
            if src != dest:
                shutil.copy2(src, dest)
            staged.append(dest)
        self._actual_output_dir = batch_root
        self._run_chunk_worker(staged, model_id)

    def _run_chunk_worker(self, md_paths: list[Path], model_id: str) -> None:
        self._progress.set(0)
        self._est = ProgressEstimator()
        self._est.on_stage("chunk")
        self._last_event_at = time.monotonic()
        self._set_busy(True)
        self._start_tick()
        self._status.set(f"切分 {len(md_paths)} 个 Markdown…")

        def on_event(ev: ChunkEvent) -> None:
            self.after(0, lambda: self._apply_chunk_event(ev))

        self._worker = ChunkWorker(
            md_paths,
            chunk_model=model_id,
            chunk_mode="auto",
            on_event=on_event,
        )
        self._worker.start()

    def _apply_chunk_event(self, ev: ChunkEvent) -> None:
        self._last_event_at = time.monotonic()
        if ev.kind == "log":
            self._log_line(ev.message)
        elif ev.kind == "progress" and ev.percent is not None:
            self._progress.set(ev.percent)
            self._status.set(ev.message)
        elif ev.kind == "done":
            self._progress.set(100)
            self._stop_tick()
            self._status.set(ev.message)
            self._log_line(ev.message)
            self._set_busy(False)
            self._open_btn.configure(state=tk.NORMAL)
            messagebox.showinfo(
                "切分完成",
                f"{ev.message}\n\n批次目录：\n{self._actual_output_dir}\n  json/ · chunks/",
            )
        elif ev.kind == "error":
            self._stop_tick()
            self._status.set("切分失败")
            self._log_line(f"[错误] {ev.message}")
            self._set_busy(False)
            messagebox.showerror("切分失败", ev.message)

    def _ensure_chunk_model(self, model_id: str) -> bool:
        ok, msg = chunk_model_status(get_models_dir(), model_id)
        if ok:
            return True
        if messagebox.askyesno("缺少切分模型", f"{msg}\n\n是否现在下载？"):
            open_chunk_download_dialog(self, model_id=model_id)
        return False

    def _on_semantic_toggle(self) -> None:
        enabled = self._semantic_chunk.get()
        self._chunk_combo.configure(state="readonly" if enabled else "disabled")
        if enabled and self._chunk_model.get() == "none":
            self._chunk_model.set("bge-base-zh-v1.5")

    def _add_paths(self, paths: list[Path]) -> None:
        existing = {self._file_list.get(i) for i in range(self._file_list.size())}
        for p in paths:
            s = str(p.resolve())
            if s not in existing and p.is_file():
                if not is_supported(p):
                    messagebox.showwarning("跳过", f"不支持的格式：{p.name}")
                    continue
                self._file_list.insert(tk.END, s)
                existing.add(s)
        n = self._file_list.size()
        self._status.set(f"已添加 {n} 个文件 — 点击「开始转换」")

    def _add_files(self) -> None:
        paths = filedialog.askopenfilenames(title="选择文件（可多选）", filetypes=_FILE_TYPES)
        if paths:
            self._add_paths([Path(p) for p in paths])

    def _add_folder(self) -> None:
        folder = filedialog.askdirectory(title="选择文件夹")
        if not folder:
            return
        exts = SUPPORTED_EXTS
        found = sorted(
            p for p in Path(folder).rglob("*") if p.is_file() and p.suffix.lower() in exts
        )
        if not found:
            messagebox.showinfo("提示", "该文件夹下没有支持的文档或图片")
            return
        self._add_paths(found)

    def _remove_selected(self) -> None:
        for i in reversed(self._file_list.curselection()):
            self._file_list.delete(i)

    def _clear_files(self) -> None:
        self._file_list.delete(0, tk.END)

    def _pick_output(self) -> None:
        path = filedialog.askdirectory(
            initialdir=self._output_dir.get() or str(app_root()),
            title="选择输出目录",
        )
        if path:
            self._output_dir.set(path)

    def _ensure_python(self) -> None:
        py = find_python(require_paddle=True)
        if py:
            set_python_path(py)

    def _pick_python(self) -> None:
        if self._busy:
            messagebox.showwarning("提示", "转换进行中，请稍候")
            return
        path = filedialog.askopenfilename(
            title="选择 Python 解释器（需已安装 paddlepaddle-gpu）",
            filetypes=[("Python", "python.exe"), ("所有文件", "*.*")],
        )
        if not path:
            return
        p = Path(path)
        from app.paths import validate_python

        if not validate_python(p):
            messagebox.showerror("无效", f"无法运行：{p}")
            return
        from app.paths import _has_paddle

        if not _has_paddle(p):
            messagebox.showerror(
                "无效",
                f"该 Python 未安装 paddlepaddle-gpu：\n{p}",
            )
            return
        set_python_path(p)
        messagebox.showinfo("已保存", f"Python 解释器：\n{p}")

    def _open_setup(self) -> None:
        if self._busy:
            messagebox.showwarning("提示", "转换进行中，请稍候")
            return
        if self._on_open_setup:
            self._on_open_setup()

    def _open_models_dir(self) -> None:
        path = get_models_dir()
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)  # type: ignore[attr-defined]

    def _open_output_dir(self) -> None:
        path = Path(getattr(self, "_actual_output_dir", None) or self._output_dir.get()).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)  # type: ignore[attr-defined]

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._convert_btn.configure(state=tk.DISABLED if busy else tk.NORMAL)
        self._chunk_btn.configure(state=tk.DISABLED if busy else tk.NORMAL)
        self._cancel_btn.configure(state=tk.NORMAL if busy else tk.DISABLED)

    def _log_line(self, text: str) -> None:
        self._log.configure(state=tk.NORMAL)
        self._log.insert(tk.END, text + "\n")
        self._log.see(tk.END)
        self._log.configure(state=tk.DISABLED)

    def _start_tick(self) -> None:
        self._stop_tick()
        self._tick_job = self.after(400, self._on_tick)

    def _stop_tick(self) -> None:
        if self._tick_job:
            self.after_cancel(self._tick_job)
            self._tick_job = None

    def _on_tick(self) -> None:
        if not self._busy:
            return
        self._tick += 1
        idle = time.monotonic() - self._last_event_at
        suffix = self._est.pulse_suffix(self._tick)
        line = self._est.status_line()
        if idle > 3 and self._est.stage in ("init", "predict"):
            line += f" {suffix}（引擎仍在运行，请稍候）"
        self._detail.set(line)
        self._progress.set(self._est.percent)
        self._tick_job = self.after(400, self._on_tick)

    def _start_convert(self) -> None:
        if self._busy:
            return

        files = self._files()
        if not files:
            messagebox.showwarning("提示", "请先添加至少一个文件")
            return

        out = Path(self._output_dir.get().strip()).expanduser().resolve()
        if out.drive.upper() == "C:":
            messagebox.showerror("错误", "输出目录不建议设在 C 盘")
            return

        root = app_root().resolve()
        try:
            out.relative_to(root)
        except ValueError:
            messagebox.showerror(
                "错误",
                f"输出目录必须在程序目录内：\n{root}\n\n当前：{out}",
            )
            return

        route = self._parse_mode.get()
        chunk = self._chunk_model.get() if self._semantic_chunk.get() else "none"
        if chunk != "none" and not self._ensure_chunk_model(chunk):
            return

        save_config(
            {
                **load_config(),
                "output_dir": str(out),
                "parse_mode": route,
                "chunk_model": chunk,
            }
        )

        need_gpu = any(needs_paddle(f, route) for f in files)
        if need_gpu:
            ok, msg = models_ready()
            if not ok:
                messagebox.showerror("模型未就绪", msg)
                return

        self._progress.set(0)
        self._est = ProgressEstimator(batch_total=len(files))
        self._est.on_batch(1, len(files))
        self._est.on_stage("init")
        self._last_event_at = time.monotonic()
        self._last_md_files = []
        self._open_btn.configure(state=tk.DISABLED)
        self._set_busy(True)
        self._start_tick()

        kw = dict(
            use_unwarping=self._unwarp.get(),
            use_orientation=self._orient.get(),
            parse_mode=route,
            chunk_model=chunk,
            on_event=self._on_parse_event,
        )

        batch_root = create_batch_dir(out)
        self._actual_output_dir = batch_root
        self._log_line(f"输出批次：{batch_root.name}")

        if len(files) == 1:
            self._worker = ParseWorker(files[0], batch_root, **kw)
        else:
            self._worker = BatchParseWorker(files, batch_root, **kw)
        self._worker.start()

    def _cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
        self._log_line("[用户取消]")
        self._set_busy(False)
        self._stop_tick()
        self._status.set("已取消")

    def _apply_event(self, ev: ParseEvent) -> None:
        self._last_event_at = time.monotonic()
        extra = ev.extra or {}

        if extra.get("batch_index"):
            self._est.on_batch(int(extra["batch_index"]), int(extra.get("batch_total") or 1))

        if ev.stage:
            tp = extra.get("total_pages")
            self._est.on_stage(ev.stage, total_pages=int(tp) if tp else None)

        if extra.get("page"):
            self._est.on_page(
                int(extra["page"]),
                total_pages=int(extra["total_pages"]) if extra.get("total_pages") else None,
            )

        if ev.percent is not None:
            self._est.percent = max(self._est.percent, ev.percent)

        if ev.kind == "log":
            self._log_line(ev.message)
        elif ev.kind == "batch":
            self._status.set(ev.message)
            self._log_line(f"▶ {ev.message}")
        elif ev.kind == "progress":
            self._status.set(ev.message)
            self._progress.set(self._est.percent)
            if ev.stage == "predict" and extra.get("page"):
                self._log_line(f"  ✓ {ev.message}")
            elif ev.stage in ("init", "restructure", "save", "models"):
                self._log_line(f"[{ev.stage}] {ev.message}")
        elif ev.kind == "done":
            self._est.on_stage("done")
            self._progress.set(100)
            self._stop_tick()
            self._status.set(ev.message)
            self._detail.set(self._est.status_line())
            self._log_line(f"✓ {ev.message}")
            self._last_md_files = list(extra.get("markdown_files") or [])
            self._open_btn.configure(state=tk.NORMAL)
            self._set_busy(False)
            n = extra.get("batch_total") or 1
            names = ", ".join(Path(p).name for p in self._last_md_files[:5])
            if len(self._last_md_files) > 5:
                names += " …"
            messagebox.showinfo(
                "转换完成",
                f"{'批量' if n > 1 else ''}完成，共 {n} 个任务。\n"
                f"批次目录：\n{self._actual_output_dir}\n"
                f"  md/ · json/ · chunks/ · assets/\n"
                f"Markdown：{names or '(见 md 目录)'}",
            )
        elif ev.kind == "error":
            self._stop_tick()
            self._status.set("失败")
            self._log_line(f"[错误] {ev.message}")
            self._set_busy(False)
            messagebox.showerror("转换失败", ev.message)

    def _on_parse_event(self, ev: ParseEvent) -> None:
        self.after(0, lambda: self._apply_event(ev))


def run_main_window(on_open_setup: Callable[[], None] | None = None) -> None:
    app = MainWindow(on_open_setup=on_open_setup)
    app.mainloop()
