# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
"""Performance + preview/export consistency audit (not part of the app, not collected by pytest).

Times each stage of the export path on one RAW (e.g. a 45 MP Nikon Z8 NEF), reports peak memory,
and compares the grid preview with the full-resolution export (both rendered with the app's own
functions, default settings), with and without sharpness.

    python tests/audit/audit_perf.py PATH.NEF [--src smneg_fixed/src]
"""
from __future__ import annotations

import argparse
import resource
import sys
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from audit_color import delta_e2000, srgb_to_lab  # noqa: E402


def rss_mb():
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024


def timed(label, fn, *a, **k):
    t = time.perf_counter()
    out = fn(*a, **k)
    print(f"  {label:<44}{time.perf_counter() - t:7.2f} s   peak RSS {rss_mb():7.0f} MB")
    return out


def render(engine, base, sharpness=0, float_out=False):
    """window.render_frame / render_frame_16bit with default settings (Natural, no crop, no straighten)."""
    out = engine.OfficialFilmEngine.apply_pipeline(base, 0, 0, 0, 0, 1.0, 1.0, 0, False, False, False,
                                                   output_float=float_out)
    if sharpness:
        blurred = cv2.GaussianBlur(out, (0, 0), sigmaX=1.0)
        a = sharpness / 100
        out = cv2.addWeighted(out, 1 + a, blurred, -a, 0)
    return out


def main():
    ap = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[2]
    ap.add_argument("raw", type=Path)
    ap.add_argument("--src", type=Path,
                    default=root / "smneg_fixed" / "src" if (root / "smneg_fixed" / "src").is_dir() else root / "src")
    args = ap.parse_args()
    sys.path.insert(0, str(args.src.resolve()))
    import smneg.engine as engine
    from smneg.export import save_image

    print(f"File: {args.raw.name}   engine: {args.src}")
    print(f"  start{'':<39}           peak RSS {rss_mb():7.0f} MB")
    full_vals = timed("decode_negative (full, LibRaw AHD demosaic)", engine.decode_negative, str(args.raw), True)
    print(f"    -> {full_vals.shape} {full_vals.dtype}, {full_vals.nbytes / 1e6:.0f} MB")
    original = engine.decode_negative
    holder = [full_vals]
    engine.decode_negative = lambda p, f: holder[0]
    base_full = timed("load_negative_base (inversion only)", engine.OfficialFilmEngine.load_negative_base, "x", True)
    engine.decode_negative = original
    holder.clear()
    full_vals = None
    timed("apply_pipeline -> uint8 (JPEG path)", render, engine, base_full)
    f16 = timed("apply_pipeline float -> uint16 (TIFF path)", lambda: np.rint(np.clip(
        render(engine, base_full, float_out=True), 0, 1) * 65535).astype(np.uint16))
    with tempfile.TemporaryDirectory() as tmp:
        timed("save_image TIFF 16-bit (deflate)", save_image, Path(tmp) / "x.tif", f16, None, file_format="tiff")
        out8 = render(engine, base_full)
        timed("save_image JPEG q100", save_image, Path(tmp) / "x.jpg", out8, None)
    del f16
    base_prev = timed("load_negative_base (preview, half-size)", engine.OfficialFilmEngine.load_negative_base,
                      str(args.raw), False)

    print("\nPreview vs export (both rendered by SMneg, export downscaled to preview size, INTER_AREA)")
    for sharp in (0, 50):
        prev = render(engine, base_prev, sharp).astype(np.float64) / 255
        full = render(engine, base_full, sharp).astype(np.float64) / 255
        full_small = cv2.resize(full, (prev.shape[1], prev.shape[0]), interpolation=cv2.INTER_AREA)
        de = delta_e2000(srgb_to_lab(prev), srgb_to_lab(full_small))
        print(f"  sharpness {sharp:>3}: dE00 mean {de.mean():.2f}  p95 {np.percentile(de, 95):.2f}  max {de.max():.1f}")
    lap = lambda img: cv2.Laplacian(cv2.cvtColor((img * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY), cv2.CV_64F).var()
    p0 = render(engine, base_prev, 0).astype(np.float64) / 255
    p50 = render(engine, base_prev, 50).astype(np.float64) / 255
    f0 = cv2.resize(render(engine, base_full, 0).astype(np.float64) / 255, p0.shape[1::-1], interpolation=cv2.INTER_AREA)
    f50 = cv2.resize(render(engine, base_full, 50).astype(np.float64) / 255, p0.shape[1::-1], interpolation=cv2.INTER_AREA)
    print(f"  sharpness 50 visible effect (Laplacian variance gain): preview x{lap(p50) / lap(p0):.2f}, "
          f"export x{lap(f50) / lap(f0):.2f}")


if __name__ == "__main__":
    main()
