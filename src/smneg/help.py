# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QVBoxLayout

from . import __version__

# All shortcuts (F1 or ?). If you change a shortcut in keyPressEvent, change it here too
SHORTCUT_SECTIONS = (
    ("Color (printer lights)", (
        ("Q / A", "Cyan + / −"),
        ("W / S", "Magenta + / −"),
        ("E / D", "Yellow + / −"),
        ("N", "Grey picker: click a neutral grey; again on a lighter / darker grey to fix highlights and shadows"),
        ("⇧N", "Clear the grey picks"),
        ("B", "Film-base picker: click the clear film rebate"),
        ("⇧B", "Film base back to automatic"),
    )),
    ("Density and tone", (
        ("↑ / ↓", "Density + / −"),
        ("⌥↑ / ⌥↓", "Contrast + / −"),
        ("⌘↑ / ⌘↓", "Saturation + / −"),
        ("T", "Tone profile: Natural → Flat → S Curve"),
        ("L", "Auto print on / off (Scientific engine; off = flat master)"),
        ("R", "Reset the frame"),
    )),
    ("Image", (
        ("← / →", "Rotate"),
        ("M", "Mirror"),
        ("C", "Auto-crop"),
        ("K", "Manual crop"),
        ("X", "Clipping preview"),
        ("P", "Pass: do not export"),
    )),
    ("Zoom", (
        ("Z", "Zoom 100 % / fit"),
        ("Scroll wheel", "Smooth zoom"),
        ("Drag", "Pan the zoomed image"),
        ("Double-click · Esc", "Back to fit"),
        ("O", "Original before inversion"),
    )),
    ("Navigation", (
        ("Space", "Grid ↔ enlarged view"),
        ("Enter · ⌘→", "Next frame"),
        ("⌘←", "Previous frame"),
        ("⇧⌘→ / ⇧⌘←", "Next / previous 6 frames"),
        ("Esc", "Back to the grid"),
    )),
    ("Settings and export", (
        ("⌘C / ⌘V", "Copy / paste settings"),
        ("H", "Hold: keep the settings for the next frames"),
        ("⌘Z / ⇧⌘Z", "Undo / redo"),
        ("⌘E", "Export"),
        ("F1 · ?", "This help"),
    )),
)


ABOUT_TEXT = "SMneg {version} · © 2026 Said Mrigua · Apache License 2.0"


def platform_keys(keys):
    """Show Ctrl / Alt / Shift on Windows and Linux; the ⌘ ⌥ ⇧ glyphs stay on macOS."""
    if sys.platform == "darwin":
        return keys
    return keys.replace("⇧⌘", "Ctrl+Shift+").replace("⌘", "Ctrl+").replace("⌥", "Alt+")


def section_html(title, rows):
    body = "".join(
        f'<tr><td style="padding:3px 14px 3px 0; white-space:nowrap;">'
        f'<span style="background-color:#2A2E32; color:#80DFAB;">&nbsp;{platform_keys(keys)}&nbsp;</span></td>'
        f'<td style="padding:3px 0; color:#E0E6EA;">{label}</td></tr>'
        for keys, label in rows
    )
    return f'<h4 style="color:#00E5FF; margin:14px 0 4px 0;">{title}</h4><table>{body}</table>'


class ShortcutsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard shortcuts")
        self.setStyleSheet(
            "QDialog { background: #1A1C1E; } QLabel { background: transparent; }"
            "QPushButton { background: #37474F; color: white; border: 1px solid #111; border-radius: 4px; padding: 6px 18px; font-weight: bold; }"
        )
        layout = QVBoxLayout(self)
        columns = QHBoxLayout()
        columns.setSpacing(28)
        half = (len(SHORTCUT_SECTIONS) + 1) // 2
        for part in (SHORTCUT_SECTIONS[:half], SHORTCUT_SECTIONS[half:]):
            label = QLabel("".join(section_html(title, rows) for title, rows in part))
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            columns.addWidget(label, 1)
        layout.addLayout(columns)
        about = QLabel(ABOUT_TEXT.format(version=__version__))
        about.setStyleSheet("color: #7F8A91; font-size: 11px;")
        layout.addWidget(about)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.clicked.connect(self.reject)
        layout.addWidget(buttons)
