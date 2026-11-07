#!/usr/bin/env python3
"""Write the sample images the browser test uploads. Usage (from backend/): python scripts/make_e2e_fixtures.py DIR"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.demo.generator import build_samples  # noqa: E402

target = Path(sys.argv[1])
target.mkdir(parents=True, exist_ok=True)
for name, data in build_samples().items():
    (target / name).write_bytes(data)
(target / "not-an-image.png").write_bytes(b"<html><script>alert(1)</script></html>")
(target / "notes.txt").write_text("Not an image.")
print(f"Wrote fixtures to {target}")
