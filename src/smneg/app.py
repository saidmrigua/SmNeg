# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
"""Application entry point."""
import sys
from pathlib import Path

from PySide6.QtGui import QColorSpace, QIcon, QSurfaceFormat
from PySide6.QtWidgets import QApplication

from .settings import APPLICATION, ORGANIZATION, migrate_legacy_settings
from .window import SMnegWindow


def use_srgb_windows() -> None:
    """The pictures are sRGB: tell the system, so a wide-gamut display shows them like the exported files
    (colour-managed) instead of stretching them to its own, more saturated primaries. Before QApplication."""
    surface = QSurfaceFormat.defaultFormat()
    surface.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.SRgb))
    QSurfaceFormat.setDefaultFormat(surface)


def main() -> int:
    use_srgb_windows()
    app = QApplication(sys.argv)
    app.setOrganizationName(ORGANIZATION)
    app.setApplicationName(APPLICATION)
    migrate_legacy_settings()
    icon = Path(__file__).with_name("assets") / "icon.png"
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))
    window = SMnegWindow()
    window.show()
    return app.exec()
