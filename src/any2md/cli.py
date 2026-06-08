"""CLI wrapper; delegates to engine.run_parser."""

from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    engine = Path(__file__).resolve().parents[2] / "engine" / "run_parser.py"
    if not engine.is_file():
        print(f"Engine not found: {engine}", file=sys.stderr)
        return 1

    import runpy

    sys.argv = [str(engine), *(argv if argv is not None else sys.argv[1:])]
    runpy.run_path(str(engine), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
