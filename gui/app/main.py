"""Application entry and flow routing."""

from __future__ import annotations

import sys


def _utf8_env() -> None:
    if sys.platform == "win32":
        import os

        os.environ.setdefault("PYTHONUTF8", "1")


def run_app(*, force_setup: bool = False) -> int:
    _utf8_env()

    from app.config import ensure_portable_config, models_ready, load_config
    from app.paths import app_root

    ensure_portable_config()
    cfg = load_config()
    setup_ok = bool(cfg.get("setup_complete"))
    models_ok, _ = models_ready()

    if force_setup or not setup_ok or not models_ok:
        from app.ui.wizard import run_wizard

        run_wizard(on_complete=_run_main)
    else:
        _run_main()

    return 0


def _run_main() -> None:
    from app.config import models_ready
    from app.ui.main_window import MainWindow

    ok, msg = models_ready()
    if not ok:
        from tkinter import messagebox

        messagebox.showerror("模型未就绪", msg)
        from app.ui.wizard import run_wizard

        run_wizard(on_complete=_run_main)
        return

    def reopen_setup() -> None:
        app.destroy()
        from app.ui.wizard import run_wizard

        run_wizard(on_complete=_run_main)

    app = MainWindow(on_open_setup=reopen_setup)
    app.mainloop()


def main() -> int:
    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())
