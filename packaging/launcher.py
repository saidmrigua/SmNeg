# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
"""Entry point used by PyInstaller.  `SMneg --self-test` checks the built bundle and exits (used by the release workflow)."""
import os
import sys


def check_engines(folder) -> str | None:
    """Invert a small scan with both engines and export it. Returns what failed, or None."""
    import cv2
    import numpy as np
    from PIL import Image

    from smneg import scientific as sc
    from smneg.engine import OfficialFilmEngine
    from smneg.export import SRGB_ICC, TIFF_METADATA_AVAILABLE, save_image

    sample = folder / "sample.tif"
    pixels = np.random.default_rng(0).integers(2000, 60000, (64, 96, 3), dtype=np.uint16)
    cv2.imwrite(str(sample), pixels)
    positive = OfficialFilmEngine.load_negative_base(str(sample), full_resolution=True)
    if positive is None or positive.shape != (64, 96, 3):
        return f"Classic inversion failed {OfficialFilmEngine.errors}"
    # Scientific engine (the default) with Auto print
    values = sc.load_linear(str(sample), full_resolution=True)
    if values is None:
        return f"Scientific load failed {OfficialFilmEngine.errors}"
    stats = sc.frame_stats(values)
    roll = sc.roll_model([stats])
    if roll is None:
        return "Scientific roll model failed"
    params = sc.frame_params(stats, roll, auto_print=True)
    preview = sc.render(values, params)
    master = sc.render(values, params, output_float=True)
    if preview.shape != (64, 96, 3) or preview.dtype != np.uint8 or not np.isfinite(master).all():
        return "Scientific render failed"
    if int(preview.max()) - int(preview.min()) < 50:
        return "Scientific render is flat"
    # exports carry the sRGB profile
    if not TIFF_METADATA_AVAILABLE:
        return "tifffile is not bundled"
    import tifffile
    tiff, jpeg = folder / "out.tif", folder / "out.jpg"
    save_image(tiff, np.rint(master * 65535).astype(np.uint16), file_format="tiff")
    save_image(jpeg, preview)
    with tifffile.TiffFile(str(tiff)) as handle:
        page = handle.pages[0]
        if page.dtype != np.uint16 or page.tags.get("InterColorProfile") is None:
            return "TIFF export without 16-bit data or ICC profile"
        if bytes(page.tags["InterColorProfile"].value) != SRGB_ICC:
            return "TIFF export with a wrong ICC profile"
    with Image.open(jpeg) as image:
        if image.info.get("icc_profile") != SRGB_ICC:
            return "JPEG export without the sRGB profile"
    return None


def self_test() -> int:   # returns 1 on failure; exits the process itself on success
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import tempfile
    from pathlib import Path

    import importlib

    importlib.import_module("rawpy")      # must be bundled
    from PySide6.QtWidgets import QApplication

    import smneg
    from smneg.window import SMnegWindow

    assets = Path(smneg.__file__).with_name("assets")
    for name in ("icon.png", "icon.ico"):
        if not (assets / name).is_file():
            print(f"self-test: missing asset {name}")
            return 1
    if getattr(sys, "frozen", False):
        licenses = assets.parent / "licenses"
        for name in ("LICENSE", "NOTICE", "THIRD_PARTY_LICENSES.md"):
            if not (licenses / name).is_file():
                print(f"self-test: missing license {name}")
                return 1
        if "Copyright 2026 Said Mrigua" not in (licenses / "NOTICE").read_text(encoding="utf-8"):
            print("self-test: missing creator attribution")
            return 1
    with tempfile.TemporaryDirectory() as folder:
        problem = check_engines(Path(folder))
        if problem:
            print(f"self-test: {problem}")
            return 1
    app = QApplication([])
    window = SMnegWindow()
    app.processEvents()
    window.shutdown_workers()
    print(f"SMneg {smneg.__version__} self-test OK", flush=True)
    os._exit(0)          # skip the normal close path: no save prompts, no lingering worker threads


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    from smneg.app import main

    sys.exit(main())
