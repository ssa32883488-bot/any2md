#!/usr/bin/env python3
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "testset" / "output"
for b in sorted(root.iterdir()):
    if not b.is_dir() or not (b / "md").is_dir():
        continue
    md = list((b / "md").glob("*.md"))
    js = list((b / "json").glob("*.json"))
    chunks = list((b / "chunks").rglob("*.md"))
    assets = [a for a in (b / "assets").rglob("*") if a.is_file()]
    print(f"=== {b.name} ===")
    print(f"md={len(md)} json={len(js)} chunk_md={len(chunks)} assets={len(assets)}")
    for m in sorted(md):
        t = m.read_text(encoding="utf-8")
        print(f"  {m.name}: {len(t)} chars, H2={t.count(chr(10)+'## ')}")
    for j in sorted(js):
        d = json.loads(j.read_text(encoding="utf-8"))
        print(f"  {j.name}: chunks={d.get('chunk_count')} mode={d.get('chunk_mode')}")
