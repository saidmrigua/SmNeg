# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
"""Entry point used by PyInstaller.  `SMneg --self-test` checks the built bundle and exits (used by the release workflow)."""
import os
import sys


def self_test() -> int:   # returns 1 on failure; exits the process itself on success
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import tempfile
    from pathlib import Path

    import cv2
    import numpy as np
    import importlib

    importlib.import_module("rawpy")      # must be bundled
    from PySide6.QtWidgets import QApplication

    import smneg
    from smneg.engine import OfficialFilmEngine
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
        sample = Path(folder) / "sample.tif"
        pixels = np.random.default_rng(0).integers(2000, 60000, (64, 96, 3), dtype=np.uint16)
        cv2.imwrite(str(sample), pixels)
        positive = OfficialFilmEngine.load_negative_base(str(sample), full_resolution=True)
        if positive is None or positive.shape != (64, 96, 3):
            print("self-test: inversion failed", OfficialFilmEngine.errors)
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
