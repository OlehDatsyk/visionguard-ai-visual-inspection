#!/usr/bin/env python3
"""Download the YOLOX-Tiny ONNX weights (Apache-2.0) and verify their checksum.

Usage (from backend/): python scripts/download_models.py [--dir PATH]
Weights are never committed to Git. Default location: backend/model_weights/ or $MODEL_DIR.
"""
import argparse
import hashlib
import os
import sys
import urllib.request
from pathlib import Path

URL = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_tiny.onnx"
SHA256 = "427cc366d34e27ff7a03e2899b5e3671425c262ea2291f88bb942bc1cc70b0f7"
FILENAME = "yolox_tiny.onnx"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    default = os.environ.get("MODEL_DIR") or str(Path(__file__).resolve().parents[1] / "model_weights")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default=default)
    target_dir = Path(parser.parse_args().dir)
    target = target_dir / FILENAME
    if target.is_file() and sha256(target) == SHA256:
        print(f"Model already installed: {FILENAME}")
        return 0
    target_dir.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".download")
    print(f"Downloading {FILENAME} (about 20 MB)...")
    try:
        urllib.request.urlretrieve(URL, temporary)
    except OSError as exc:
        print(f"Download failed: {exc}. Object detection stays unavailable until this succeeds.", file=sys.stderr)
        temporary.unlink(missing_ok=True)
        return 1
    if sha256(temporary) != SHA256:
        temporary.unlink(missing_ok=True)
        print("Checksum mismatch: the downloaded file was discarded.", file=sys.stderr)
        return 1
    temporary.replace(target)
    print(f"Installed {FILENAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
