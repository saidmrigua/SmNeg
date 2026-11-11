# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
from __future__ import annotations

import copy
import dataclasses
import json
from collections import OrderedDict
import os
import sys
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np
from rawpy import LibRawError
from PySide6.QtCore import QPointF, QProcess, QTimer, Qt, QUrl
from PySide6.QtGui import QCursor, QDesktopServices, QFont, QKeyEvent
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel,
    QMainWindow, QMenu,
    QMessageBox, QProgressDialog, QPushButton, QSlider, QStackedWidget, QVBoxLayout, QWidget
)

from .settings import app_settings
from .camera_reference import camera_differences, read_camera_reference
from .capture import (
    ACCESSIBILITY_REQUIRED, ACCESSIBILITY_SETTINGS, CAPTURE_SCRIPT, NX_TETHER_PATH, SHOOT_SHORTCUT,
)
from .crop import ManualCropDialog, apply_crop, reorient, straighten_image
from . import film_profile as fp
from . import scientific as sc
from .engine import OfficialFilmEngine, decode_negative, source_max_edge, tone_curve
from .flat_field import RAW_EXTENSIONS, build_flat_field
from .export import (
    TIFF_METADATA_AVAILABLE, ExportDialog, SessionInfoDialog, create_export_folder, format_duration, save_image,
)
from .help import ShortcutsDialog
from .hot_folder import HotFolder
from .models import FrameItem
from .session import (
    ENGINES, FRAME_FIELDS, METERS, create_session_folder, load_session, project_path, read_project, save_session, write_project,
)
from .zoom import ZoomDialog
from .views import EnlargedView, FrameCard, mark_passed

SUPPORTED_EXTS = tuple(sorted(RAW_EXTENSIONS)) + ('.tif', '.tiff', '.jpg', '.jpeg', '.png')
ENGINE_LABELS = {"scientific": "Scientific", "classic": "Classic"}


def fp_safe_name(name: str) -> str:
    """File name for a profile: keeps letters, digits, spaces, - and _."""
    cleaned = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in name).strip()
    return cleaned[:80] or "film_profile"
_DEFAULT = object()


class SMnegWindow(QMainWindow):
    PAGE_SIZE = 6
    RESTORE_WORKERS = 2

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SMneg | Film Negative Inversion")
        self.resize(1380, 890)
        self.setStyleSheet("background-color: #1A1C1E; color: #FFFFFF;")

        self.items: List[FrameItem] = []
        self.current_idx = 0
        self.current_page = 0
        self.copied_settings: Optional[dict] = None
        self.held_settings: Optional[dict] = None
        self.undo_stack: list = []
        self.redo_stack: list = []
        self.last_edit = None

        self.session_folder = None
        self.camera_reference = {}
        self.session_info = {}
        self.session_timer = QTimer(self)
        self.session_timer.setSingleShot(True)
        self.session_timer.setInterval(700)
        self.session_timer.timeout.connect(self.persist_project)
        self.hot_folder = None
        self.failed_imports = set()
        self.hot_timer = QTimer(self)
        self.hot_timer.setInterval(2000)
        self.hot_timer.timeout.connect(self.import_hot_folder)
        self.flat_path = None
        self.flat_gain = None
        self.opening_tether = False
        self.capture_process = QProcess(self)
        self.capture_process.finished.connect(self.capture_finished)
        self.capture_process.errorOccurred.connect(self.capture_process_error)
        self.zoom_worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="smneg-zoom")
        self.zoom_item = None
        self.zoom_base = None
        self.zoom_cache = None
        self.zoom_future = None
        self.zoom_version = 0
        self.zoom_timer = QTimer(self)
        self.zoom_timer.setInterval(60)
        self.zoom_timer.timeout.connect(self.poll_zoom_job)
        self.zoom_refresh_timer = QTimer(self)
        self.zoom_refresh_timer.setSingleShot(True)
        self.zoom_refresh_timer.setInterval(250)
        self.zoom_refresh_timer.timeout.connect(self.start_zoom_job)
        self.restoring_frames = False
        engine = app_settings().value("engine", "scientific", type=str)
        self.engine = engine if engine in ENGINES else "scientific"
        self._roll_cache = None
        self._log_cache = OrderedDict()
        self.camera_profile = None          # scientific.CameraProfile (camera + light, from an IT8 target)
        self.film_profile = None            # film_profile.FilmProfile (film + rig, from a chart shot on the film)
        self.film_profile_path = ""
        self.chart_points = []
        meter = app_settings().value("meter", "frame", type=str)
        self.meter = meter if meter in METERS else "frame"     # how much Auto print follows each frame
        self.base_reference = None           # film base measured on scans of clear film (the roll's leader)
        self.base_reference_files = []
        self.camera_profile_path = ""
        self._camera_matrix = None
        self.restore_worker = ThreadPoolExecutor(max_workers=self.RESTORE_WORKERS, thread_name_prefix="smneg-restore")
        self.init_ui()
        QTimer.singleShot(50, self.restore_startup)

    def init_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Top Bar
        top_bar = QFrame()
        top_bar.setStyleSheet("background-color: #121415; border-radius: 4px; padding: 4px;")
        tbl = QHBoxLayout(top_bar)
        tbl.setContentsMargins(10, 4, 10, 4)

        brand = QLabel("SMneg")
        brand.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        brand.setStyleSheet("color: #00E5FF;")
        tbl.addWidget(brand)

        self.lbl_batch_indicator = QLabel("Batch 1 (Frames 1-6)")
        self.lbl_batch_indicator.setFont(QFont("Arial", 10))
        self.lbl_batch_indicator.setStyleSheet("color: #FFB300; margin-left: 8px;")
        tbl.addWidget(self.lbl_batch_indicator)

        tbl.addStretch()

        self.lbl_count = QLabel("0 FRAMES")
        self.lbl_count.setStyleSheet("background: #004D40; color: #80DFAB; padding: 3px 8px; border-radius: 3px;")
        tbl.addWidget(self.lbl_count)

        self.lbl_feed = QLabel("Semi Mode")
        self.lbl_feed.setStyleSheet("background: #263238; color: #ECEFF1; padding: 3px 8px; border-radius: 3px;")
        tbl.addWidget(self.lbl_feed)

        btn_load = QPushButton("Select Roll Folder")
        btn_load.setStyleSheet("background: #0277BD; color: white; padding: 5px 12px; font-weight: bold;")
        btn_load.clicked.connect(self.select_roll_folder)
        tbl.addWidget(btn_load)
        self.btn_session = self.make_btn(tbl, "NEW SESSION", self.new_session, "#006064")
        self.btn_session_info = self.make_btn(tbl, "SESSION INFO", self.edit_session_info, "#006064")
        self.btn_hot_folder = QPushButton("HOT FOLDER")
        self.btn_hot_folder.setStyleSheet(btn_load.styleSheet())
        hot_menu = QMenu(self.btn_hot_folder)
        hot_menu.addAction("Choose Nikon folder…", self.choose_hot_folder)
        self.watch_session_action = hot_menu.addAction("Watch the session folder", self.watch_session_folder)
        self.watch_session_action.setEnabled(False)
        self.stop_hot_action = hot_menu.addAction("Stop watching", self.stop_hot_folder)
        self.stop_hot_action.setEnabled(False)
        self.btn_hot_folder.setMenu(hot_menu)
        tbl.addWidget(self.btn_hot_folder)
        self.btn_capture = self.make_btn(tbl, "CAPTURE", self.capture_image, "#006064")
        if sys.platform == "darwin":
            self.btn_capture.setToolTip(f"NX Tether · Shoot shortcut {SHOOT_SHORTCUT}")
        else:
            self.btn_capture.setEnabled(False)
            self.btn_capture.setToolTip("Nikon NX Tether capture is only available on macOS.")

        self.make_btn(tbl, "ZOOM 100% [Z]", self.open_zoom, "#37474F")
        self.btn_flat = self.make_btn(tbl, "FLAT FIELD", self.choose_flat_field, "#37474F")
        self.make_btn(tbl, "ORIGINAL [O]", self.open_original, "#37474F")
        self.make_btn(tbl, "? [F1]", self.show_shortcuts, "#37474F")

        layout.addWidget(top_bar)

        # QStackedWidget
        self.stack = QStackedWidget()

        # Grid view (6 frames)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(8)
        self.cards: List[FrameCard] = []
        for i in range(self.PAGE_SIZE):
            card = FrameCard(i)
            card.clicked.connect(self.on_frame_click)
            card.doubleClicked.connect(self.switch_to_large_view)
            self.cards.append(card)
            self.grid.addWidget(card, i // 3, i % 3)
        self.stack.addWidget(self.grid_host)

        # Enlarged View
        self.large_preview = EnlargedView()
        self.large_preview.doubleClicked.connect(self.switch_to_grid_view)
        self.large_preview.canvas.zoomStarted.connect(self.begin_zoom)
        self.large_preview.canvas.zoomEnded.connect(self.end_zoom)
        self.large_preview.canvas.pointPicked.connect(self.on_point_picked)
        self.pick_kind = None
        self.stack.addWidget(self.large_preview)

        layout.addWidget(self.stack, stretch=1)

        self.lbl_info = QLabel("")
        self.lbl_info.setFont(QFont("Consolas", 9))
        self.lbl_info.setStyleSheet("color: #9AA5AB; background: #121415; padding: 4px 10px; border-radius: 3px;")
        layout.addWidget(self.lbl_info)

        # Keypad Panel
        self.keypad = QFrame()
        self.keypad.setStyleSheet("background-color: #141517; border: 1px solid #26282B; border-radius: 4px; padding: 6px;")
        kpl = QHBoxLayout(self.keypad)

        # CMY Keys
        cmy_box = QVBoxLayout()
        lbl_c = QLabel("COLOR BALANCE (PRINTER LIGHTS)")
        lbl_c.setFont(QFont("Arial", 8, QFont.Weight.Bold))
        lbl_c.setStyleSheet("color: #888;")
        cmy_box.addWidget(lbl_c)
        cmy_r = QHBoxLayout()
        self.make_btn(cmy_r, "+C [Q]", lambda: self.adjust_color("C", 1), "#006064")
        self.make_btn(cmy_r, "-C (+R) [A]", lambda: self.adjust_color("C", -1), "#BF360C")
        self.make_btn(cmy_r, "+M [W]", lambda: self.adjust_color("M", 1), "#880E4F")
        self.make_btn(cmy_r, "-M (+G) [S]", lambda: self.adjust_color("M", -1), "#1B5E20")
        self.make_btn(cmy_r, "+Y [E]", lambda: self.adjust_color("Y", 1), "#F57F17")
        self.make_btn(cmy_r, "-Y (+B) [D]", lambda: self.adjust_color("Y", -1), "#0D47A1")
        self.make_btn(cmy_r, "CLR COLOR", self.clear_color, "#424242")
        cmy_box.addLayout(cmy_r)
        kpl.addLayout(cmy_box)

        kpl.addWidget(self.v_sep())

        # Density Keys
        den_box = QVBoxLayout()
        lbl_d = QLabel("DENSITY (EXPOSURE)")
        lbl_d.setFont(QFont("Arial", 8, QFont.Weight.Bold))
        lbl_d.setStyleSheet("color: #888;")
        den_box.addWidget(lbl_d)
        den_r = QHBoxLayout()
        self.make_btn(den_r, "+1D [↑]", lambda: self.adjust_density(1), "#37474F")
        self.make_btn(den_r, "+3D", lambda: self.adjust_density(3), "#263238")
        self.make_btn(den_r, "-1D [↓]", lambda: self.adjust_density(-1), "#455A64")
        self.make_btn(den_r, "-3D", lambda: self.adjust_density(-3), "#546E7A")
        self.make_btn(den_r, "N (0)", self.clear_density, "#424242")
        den_box.addLayout(den_r)
        # labels and menus set their own style: the keypad frame's border and padding would box them in
        label_style = "color: #888; border: none; padding: 0px; background: transparent;"
        combo_style = ("QComboBox { background: #26282B; color: white; border: 1px solid #37474F; "
                       "border-radius: 3px; padding: 3px 8px; }")
        menu_style = "background: #37474F; color: white; border: 1px solid #111; padding: 5px 10px; font-weight: bold;"

        def row_label(text):
            label = QLabel(text)
            label.setFont(QFont("Arial", 8, QFont.Weight.Bold))
            label.setStyleSheet(label_style)
            return label

        tone_row = QHBoxLayout()
        tone_row.addWidget(row_label("TONE"))
        self.tone_profile = QComboBox()
        self.tone_profile.addItems(["Natural", "Flat", "S Curve"])
        self.tone_profile.setStyleSheet(combo_style)
        self.tone_profile.setMinimumWidth(96)
        self.tone_profile.activated.connect(self.change_tone_profile)
        tone_row.addWidget(self.tone_profile)

        engine_row = QHBoxLayout()
        engine_row.addWidget(row_label("ENGINE"))
        self.engine_box = QComboBox()
        self.engine_box.setStyleSheet(combo_style)
        self.engine_box.setMinimumWidth(120)
        for key in ENGINES:
            self.engine_box.addItem(ENGINE_LABELS[key], key)
        self.engine_box.setToolTip(
            "Scientific: measured film base, density, roll-level neutral balance, sRGB output.\n"
            "Classic: the original SMneg inversion (per-frame auto levels).")
        self.engine_box.activated.connect(self.change_engine)
        engine_row.addWidget(self.engine_box)
        self.sync_engine_box()
        self.btn_profile = QPushButton("CAMERA: none")
        self.btn_profile.setStyleSheet(menu_style)
        self.btn_profile.setMinimumWidth(150)
        profile_menu = QMenu(self.btn_profile)
        profile_menu.addAction("Load camera profile (IT8 .json)…", self.choose_camera_profile)
        profile_menu.addAction("No camera profile", lambda: self.set_camera_profile(""))
        self.btn_profile.setMenu(profile_menu)
        engine_row.addWidget(self.btn_profile)
        self.btn_film = QPushButton("FILM: auto")
        self.btn_film.setStyleSheet(menu_style)
        self.btn_film.setMinimumWidth(150)
        film_menu = QMenu(self.btn_film)
        film_menu.addAction("Calibrate from a ColorChecker on this frame…", lambda: self.start_pick("chart"))
        film_menu.addAction("Save this roll's colour balance as a film profile…", self.save_roll_balance)
        film_menu.addAction("Load film profile…", self.choose_film_profile)
        film_menu.addAction("Automatic (no film profile)", lambda: self.set_film_profile(""))
        film_menu.addSeparator()
        film_menu.addAction("Film base reference from scans of clear film (leader)…", self.choose_base_reference)
        film_menu.addAction("Remove film base reference", lambda: self.set_base_reference(None))
        self.btn_film.setMenu(film_menu)
        self.btn_film.setToolTip("Film profile: crosstalk, dye balance and contrast measured on a ColorChecker\n"
                                 "photographed on the film and scanned on this set-up (Scientific engine).")
        engine_row.addWidget(self.btn_film)
        engine_row.addWidget(row_label("METER"))
        self.meter_box = QComboBox()
        self.meter_box.setStyleSheet(combo_style)
        self.meter_box.setMinimumWidth(105)
        for key, text in (("frame", "Frame"), ("balanced", "Balanced"), ("roll", "Roll lock")):
            self.meter_box.addItem(text, key)
        self.meter_box.setToolTip(
            "Auto print exposure and contrast (the colour always comes from the roll):\n"
            "Frame: each frame fills black to white on its own (default).\n"
            "Balanced: half frame, half roll.\n"
            "Roll lock: one setting for the whole roll; the same tone prints the same in every frame.")
        self.meter_box.setCurrentIndex(max(0, self.meter_box.findData(self.meter)))
        self.meter_box.activated.connect(self.change_meter)
        engine_row.addWidget(self.meter_box)
        engine_row.addStretch()
        self.btn_auto_print = self.make_btn(tone_row, "AUTO PRINT [L]", self.toggle_auto_print, "#00695C")
        self.btn_auto_print.setToolTip(
            "Scientific engine: automatic print exposure and contrast for each frame, the same for the three\n"
            "channels (greys stay grey). Off: the flat master (scene contrast 1:1).")
        self.make_btn(tone_row, "RESET [R]", self.reset_frame, "#424242")
        den_box.addLayout(tone_row)
        kpl.addLayout(den_box)

        kpl.addWidget(self.v_sep())

        # Operations
        op_box = QVBoxLayout()
        lbl_o = QLabel("OPERATIONAL CONTROLS")
        lbl_o.setFont(QFont("Arial", 8, QFont.Weight.Bold))
        lbl_o.setStyleSheet("color: #888;")
        op_box.addWidget(lbl_o)
        op_r = QHBoxLayout()
        self.make_btn(op_r, "ROTATE [←/→]", self.rotate_cw, "#00838F")
        self.make_btn(op_r, "MIRROR [M]", self.toggle_mirror, "#00838F")
        self.btn_hold = self.make_btn(op_r, "HOLD [H]", self.toggle_hold, "#E65100")
        self.make_btn(op_r, "PASS [P]", self.toggle_pass, "#B71C1C")
        self.make_btn(op_r, "◀ PREV 6 [⇧⌘←]", self.prev_batch_six, "#37474F")
        self.make_btn(op_r, "NEXT 6 [⇧⌘→]", self.next_batch_six, "#2E7D32")
        edit_r = QHBoxLayout()
        self.make_btn(edit_r, "UNDO [⌘Z]", self.undo, "#455A64")
        self.make_btn(edit_r, "REDO [⇧⌘Z]", self.redo, "#455A64")
        self.make_btn(edit_r, "MANUAL CROP [K]", self.open_manual_crop, "#37474F")
        self.make_btn(edit_r, "SHARPNESS", self.open_sharpness, "#37474F")
        self.make_btn(edit_r, "EXPORT PIC [⌘E]", self.export_batch, "#00C853")
        op_box.addLayout(op_r)
        op_box.addLayout(edit_r)
        kpl.addLayout(op_box)

        layout.addWidget(self.keypad)

        self.btn_grey_pick = self.make_btn(engine_row, "GREY PICK [N]", lambda: self.start_pick("grey"), "#37474F")
        self.btn_grey_pick.setToolTip("Click something that should be neutral grey: sets C and Y (Scientific engine)")
        self.btn_base_pick = self.make_btn(engine_row, "BASE PICK [B]", lambda: self.start_pick("base"), "#37474F")
        self.btn_base_pick.setToolTip("Click the clear film between frames (rebate): sets the film base for the roll.\n"
                                      "⇧B returns to automatic detection.")
        # set-up bar: what the roll is rendered with (engine, profiles, meter); full window width
        self.setup_bar = QFrame()
        self.setup_bar.setStyleSheet("background-color: #141517; border: 1px solid #26282B; border-radius: 4px;")
        engine_row.setContentsMargins(8, 4, 8, 4)
        self.setup_bar.setLayout(engine_row)
        layout.addWidget(self.setup_bar)

        # buttons and combos never take focus, so Space and the arrow keys always reach the keyboard handler
        for kind in (QPushButton, QComboBox):
            for widget in self.findChildren(kind):
                widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def make_btn(self, layout: QHBoxLayout, text: str, cb, color: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        btn.setStyleSheet(f"background-color: {color}; color: white; border: 1px solid #111; padding: 6px 10px; border-radius: 3px;")
        btn.clicked.connect(cb)
        layout.addWidget(btn)
        return btn

    def v_sep(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("color: #333;")
        return sep

    def render_item(self, item: FrameItem) -> np.ndarray:
        return self.render_frame(item, item.base_positive, show_clipping=item.show_clipping)

    def render_frame(self, item, base_positive, *, show_clipping=False, edit_crop=False, output_16bit=False,
                     params=None):
        if self.engine == "scientific":
            params = params or self.frame_params(item)
            rendered = sc.render(
                None, params, log_e=self.log_exposure(item, base_positive, params),
                camera_matrix=self._camera_matrix,
                cyan=item.cyan, magenta=item.magenta, yellow=item.yellow, density=item.density,
                contrast=item.contrast, saturation=item.saturation, profile=item.tone_profile,
                rotation=item.rotation, mirror=item.mirror,
                auto_crop=item.auto_crop and item.manual_crop is None and not edit_crop,
                show_clipping=show_clipping and not output_16bit, output_float=output_16bit,
            )
            if not edit_crop:
                rendered = straighten_image(rendered, item.straighten)
            rendered = self.sharpen(rendered, item.sharpness)
            if edit_crop:
                return rendered
            rendered = apply_crop(rendered, item.manual_crop)
            if output_16bit:  # in place: the float array is ours, and a 45 MP copy costs 550 MB
                np.clip(rendered, 0.0, 1.0, out=rendered)
                rendered *= 65535.0
                np.rint(rendered, out=rendered)
                return rendered.astype(np.uint16)
            return rendered
        if output_16bit:
            return self.render_frame_16bit(item, base_positive)
        rendered = OfficialFilmEngine.apply_pipeline(
            base_positive=base_positive,
            cyan_points=item.cyan,
            magenta_points=item.magenta,
            yellow_points=item.yellow,
            density_step=item.density,
            contrast=item.contrast,
            saturation=item.saturation,
            rotation=item.rotation,
            mirror=item.mirror,
            auto_crop=item.auto_crop and item.manual_crop is None and not edit_crop,
            show_clipping=show_clipping and item.tone_profile == "Natural",
        )
        if item.tone_profile != "Natural":
            curve = tone_curve(np.linspace(0, 1, 256), item.tone_profile)
            rendered = cv2.LUT(rendered, np.rint(curve * 255).astype(np.uint8))
            if show_clipping:
                rendered[np.all(rendered >= 250, axis=-1)] = [255, 0, 0]
                rendered[np.all(rendered <= 5, axis=-1)] = [0, 0, 255]
        if not edit_crop:
            rendered = straighten_image(rendered, item.straighten)
        rendered = self.sharpen(rendered, item.sharpness)
        return rendered if edit_crop else apply_crop(rendered, item.manual_crop)

    @staticmethod
    def sharpen(image, sharpness):
        """Unsharp mask whose radius follows the image size, so preview and export look the same
        (the radius is 1 px on a 1600 px preview and scales up at full resolution)."""
        if not sharpness:
            return image
        sigma = max(1.0, max(image.shape[:2]) / 1600)
        blurred = cv2.GaussianBlur(image, (0, 0), sigmaX=sigma)
        amount = sharpness / 100
        return cv2.addWeighted(image, 1 + amount, blurred, -amount, 0)

    # ==========================================================================
    # SCIENTIFIC ENGINE: per-frame statistics, roll model, cached inversion
    # ==========================================================================
    def ensure_stats(self, item):
        if item.stats is None and item.base_positive is not None:
            item.stats = sc.frame_stats(item.base_positive)
        return item.stats

    def stats_for(self, item):
        """Frame statistics, with the film base the user picked (if any) instead of the detected one."""
        stats = self.ensure_stats(item)
        if stats is None or item.base_pick is None:
            return stats
        return dataclasses.replace(stats, base=np.asarray(item.base_pick, np.float32), source="picked")

    def roll(self):
        """Film base, dye balance and exposure reference shared by every frame of the roll."""
        key = tuple((id(self.ensure_stats(item)), tuple(item.base_pick) if item.base_pick else None)
                    for item in self.items)
        if self._roll_cache is None or self._roll_cache[0] != key:
            stats = [self.stats_for(item) for item in self.items]
            self._roll_cache = (key, sc.roll_model([s for s in stats if s is not None], self.film_profile,
                                                   self.base_reference))
        return self._roll_cache[1]

    def frame_params(self, item):
        stats = self.stats_for(item)
        roll = self.roll() if any(other is item for other in self.items) else None
        return sc.frame_params(stats, roll or sc.roll_model([stats], self.film_profile), self.film_profile,
                               auto_print=bool(getattr(item, "auto_print", True)),
                               meter=sc.METER_STRENGTHS[self.meter], grey_picks=item.grey_picks)

    def log_exposure(self, item, values, params):
        """Inversion of the preview, cached for the frames on screen (keys only change the look-up)."""
        if values is not item.base_positive:
            return sc.scene_log_exposure(values, params)
        key = (id(values), params.base.tobytes(), params.slopes.tobytes(), params.anchor, params.mono, params.gamma,
               None if params.crosstalk is None else params.crosstalk.tobytes(),
               params.balance, None if params.bounds is None else params.bounds.tobytes())
        hit = self._log_cache.get(id(item))
        if hit is not None and hit[0] == key:
            self._log_cache.move_to_end(id(item))
            return hit[1]
        log_e = sc.scene_log_exposure(values, params)
        self._log_cache[id(item)] = (key, log_e)
        self._log_cache.move_to_end(id(item))
        while len(self._log_cache) > self.PAGE_SIZE + 2:
            self._log_cache.popitem(last=False)
        return log_e

    def change_meter(self, index):
        self.set_meter(self.meter_box.itemData(index))

    def set_meter(self, meter, quiet=False):
        self.meter = meter if meter in METERS else "frame"
        self.meter_box.setCurrentIndex(max(0, self.meter_box.findData(self.meter)))
        self._log_cache.clear()
        self.zoom_cache = None
        if not quiet:
            app_settings().setValue("meter", self.meter)
            self.persist_project()
            if self.items:
                self.refresh_current_view()

    def sync_engine_box(self):
        self.engine_box.setCurrentIndex(max(0, self.engine_box.findData(self.engine)))

    def change_engine(self, index):
        engine = self.engine_box.itemData(index)
        if engine == self.engine:
            return
        if self.items:
            answer = QMessageBox.question(
                self, "Engine",
                f"Switch to the {ENGINE_LABELS[engine]} engine? All {len(self.items)} frames are re-read "
                "(your color, density and crop settings are kept, but the same keys give a different result).",
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.sync_engine_box()
                return
        previous = self.engine
        self.engine = engine
        if not self.reload_previews():      # nothing was replaced: the previous previews are still there
            self.engine = previous
            self._log_cache.clear()
            self._roll_cache = None
            self.sync_engine_box()
            return
        app_settings().setValue("engine", engine)
        self.persist_project()
        self.refresh_current_view()

    # ==========================================================================
    # PICKERS: neutral grey (sets C/Y) and film base (rebate), Scientific engine
    # ==========================================================================
    PICK_RADIUS = 0.004          # half-size of the sampled square, fraction of the long side

    def start_pick(self, kind):
        item = self.current_item()
        if item is None:
            return
        if self.engine != "scientific":
            QMessageBox.information(self, "Pickers", "The grey and film-base pickers need the Scientific engine "
                                                     "(ENGINE menu).")
            return
        if self.stack.currentIndex() == 0:
            self.switch_to_large_view(self.current_idx)
        self.pick_kind = kind
        self.chart_points = []
        self.large_preview.canvas.set_pick_mode(True)
        if kind == "chart":
            self.statusBar().showMessage(
                "Click the centres of the 4 corner patches of the ColorChecker (dark skin, bluish green, white, "
                "black), in any order  ·  1/4  ·  Esc cancels")
            return
        what = ("a neutral grey or white (not clipped, not deep shadow)" if kind == "grey"
                else "the clear film between the frames (rebate), not the bare light")
        self.statusBar().showMessage(f"Click {what}  ·  Esc cancels")

    def cancel_pick(self):
        self.pick_kind = None
        self.large_preview.canvas.set_pick_mode(False)
        self.statusBar().showMessage("Pick cancelled", 2000)

    def source_point(self, item, u, v):
        """Point (u, v, 0..1) of the displayed frame -> (x, y) pixel of the scan (item.base_positive).

        A grid of source coordinates goes through exactly the geometry of the rendering
        (mirror, rotation, auto-crop, straighten, manual crop), so the mapping cannot drift from it."""
        h, w = item.base_positive.shape[:2]
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        grid = np.dstack([xs, ys, np.zeros_like(xs)])
        if item.mirror:
            grid = np.fliplr(grid)
        steps = (item.rotation % 360) // 90
        if steps:
            grid = np.rot90(grid, -steps)
        if item.auto_crop and item.manual_crop is None:
            gh, gw = grid.shape[:2]
            grid = grid[int(gh * 0.05):int(gh * 0.95), int(gw * 0.05):int(gw * 0.95)]
        grid = apply_crop(straighten_image(np.ascontiguousarray(grid), item.straighten), item.manual_crop)
        gh, gw = grid.shape[:2]
        x, y = grid[min(gh - 1, int(v * gh)), min(gw - 1, int(u * gw)), :2]
        return int(np.clip(round(float(x)), 0, w - 1)), int(np.clip(round(float(y)), 0, h - 1))

    def pick_region(self, item, x, y):
        h, w = item.base_positive.shape[:2]
        r = max(2, round(self.PICK_RADIUS * max(h, w)))
        return slice(max(0, y - r), min(h, y + r + 1)), slice(max(0, x - r), min(w, x + r + 1))

    def on_point_picked(self, u, v):
        kind, self.pick_kind = self.pick_kind, None
        item = self.current_item()
        if kind is None or item is None or self.engine != "scientific":
            return
        x, y = self.source_point(item, u, v)
        if kind == "chart":
            self.chart_points.append((x, y))
            if len(self.chart_points) < 4:
                self.pick_kind = "chart"
                self.large_preview.canvas.set_pick_mode(True)
                self.statusBar().showMessage(
                    f"Corner patch {len(self.chart_points) + 1}/4 of the ColorChecker  ·  Esc cancels")
                return
            points, self.chart_points = self.chart_points, []
            self.calibrate_film_from_chart(item, points)
            return
        region = self.pick_region(item, x, y)
        if kind == "grey":
            self.apply_grey_pick(item, region)
        else:
            self.apply_base_pick(item, region)

    def apply_grey_pick(self, item, region):
        values = item.base_positive[region]
        params = self.frame_params(item)
        level = sc.region_log_exposure(item.base_positive, params, region)
        if values.max() >= sc.SATURATED or level[1] < -1.6 or level[1] > 1.2:
            self.statusBar().showMessage("Pick a mid-tone grey: this point is clipped, too dark or too bright.", 6000)
            return
        picked = [float(v) for v in np.median(values.reshape(-1, 3), axis=0)]
        picks = ((item.grey_picks or []) + [picked])[-self.MAX_GREY_PICKS:]
        self.begin_edit()
        if len(picks) == 1:      # one grey: an offset, shown on the C and Y keys
            cyan, magenta, yellow = sc.neutral_points(item.base_positive, params, region, item.magenta)
            clipped = any(abs(value) > 50 for value in (cyan, yellow))
            item.cyan, item.yellow = max(-50, min(50, cyan)), max(-50, min(50, yellow))
            item.grey_picks = picks
            self.refresh_current_view()
            message = (f"Grey set: C{item.cyan:+d} M{item.magenta:+d} Y{item.yellow:+d}"
                       + ("  (limited to ±50)" if clipped else "")
                       + "  ·  N on a lighter or darker grey also corrects highlights and shadows")
        else:                    # several greys: offset and tilt of the red and blue layers (not on the keys)
            item.grey_picks = picks
            item.cyan = item.yellow = item.magenta
            balance = self.frame_params(item).balance
            self.refresh_current_view()
            tilted = balance is not None and (abs(balance[0] - 1) > 1e-6 or abs(balance[2] - 1) > 1e-6)
            message = (f"{len(picks)} greys: balance and tilt set (R ×{balance[0]:.3f}, B ×{balance[2]:.3f})" if tilted
                       else f"{len(picks)} greys of similar brightness: balance set; pick a much lighter or darker "
                            "grey to correct the tilt")
            message += "  ·  ⇧N clears the grey picks"
        self.statusBar().showMessage(message, 8000)

    MAX_GREY_PICKS = 5

    def clear_grey_picks(self):
        item = self.current_item()
        if item is None or not item.grey_picks:
            return
        self.begin_edit()
        item.grey_picks = None
        item.cyan = item.yellow = item.magenta
        self.refresh_current_view()
        self.statusBar().showMessage("Grey picks cleared", 4000)

    def apply_base_pick(self, item, region):
        values = item.base_positive[region].reshape(-1, 3)
        if values.max() >= sc.SATURATED:
            self.statusBar().showMessage("This point is clipped (bare light?). Pick the clear film instead.", 6000)
            return
        base = np.median(values, axis=0)
        orange = np.log10(base[2]) - np.log10(base[0])
        stats = self.ensure_stats(item)
        mono = stats is not None and stats.mono
        frame = np.log10(np.clip(item.base_positive.reshape(-1, 3), 1e-5, None))
        film = frame[frame.max(-1) < np.log10(sc.SATURATED)]
        if not mono:   # compare with film only: bare light (no orange mask) is always clearer
            film = film[np.abs((film[:, 2] - film[:, 0]) - orange) < 0.35]
        clearer = np.mean(np.all(film > np.log10(base) + 0.03, axis=-1)) if len(film) else 0.0
        if clearer > 0.01 or (not mono and orange > -0.15):
            reason = ("Parts of the film are clearer than this point" if clearer > 0.01
                      else "This point has no orange mask (bare light?)")
            if QMessageBox.question(self, "Film base", f"{reason}. Use it as the film base anyway?") \
                    != QMessageBox.StandardButton.Yes:
                return
        self.begin_edit()
        item.base_pick = [float(v) for v in base]
        self.refresh_current_view()
        self.statusBar().showMessage(
            "Film base set from this frame: used here and for the frames of the roll without a visible rebate "
            "(⇧B = automatic).", 8000)

    # ==========================================================================
    # FILM PROFILE (ColorChecker photographed on the film: crosstalk, dye balance, contrast)
    # ==========================================================================
    @staticmethod
    def film_profile_dir() -> Path:
        return Path.home() / "Documents" / "SmNeg" / "film_profiles"

    def calibrate_film_from_chart(self, item, points):
        raw = item.base_positive                               # linear scan (the profile acts at render only)
        if item.base_pick is not None:
            base, origin = np.asarray(item.base_pick, float), "picked"
        else:
            base, origin = sc.estimate_base(raw)
        quad = fp._order_quad(points)
        sides = np.linalg.norm(quad - np.roll(quad, -1, axis=0), axis=1)
        radius = max(2.0, 0.22 * float(np.min(sides)) / (fp.ROWS - 1))
        _, patches = fp.best_layout(raw, points, base, radius)
        if np.any(patches.max(1) >= sc.SATURATED):
            QMessageBox.warning(self, "Film calibration", "Some patches are clipped in the scan. Scan with less "
                                                           "exposure (or flat field) and retry.")
            return
        film = self.session_info.get("film", "") if isinstance(self.session_info, dict) else ""
        default = f"{film or 'Film'} {datetime.now():%Y-%m-%d}"
        profile = fp.fit_film_profile(patches, base, name=default)
        note = "" if origin in ("rebate", "picked") else (
            "\n\nNote: no rebate was found on this frame; the film base was estimated. Pick it with B "
            "for a more precise calibration.")
        text = (f"Chart colour error (CIEDE2000, mean of 24 patches):\n"
                f"   without crosstalk correction: {profile.delta_e_before:.2f}\n"
                f"   with the calibrated profile:  {profile.delta_e_after:.2f}\n"
                f"Grey patches chroma: {profile.grey_chroma_after:.2f}\n"
                f"Film contrast (gamma): {profile.gamma:.3f}{note}\n\nName of the film profile:")
        name, ok = QInputDialog.getText(self, "Film calibration", text, text=default)
        if not ok or not name.strip():
            return
        profile.name = name.strip()
        profile.source = Path(item.path).name
        path = self.film_profile_dir() / (fp_safe_name(profile.name) + ".json")
        try:
            profile.save(path)
        except OSError as error:
            QMessageBox.warning(self, "Film calibration", f"Unable to save the profile: {error}")
            return
        self.set_film_profile(str(path))

    MIN_BALANCE_FRAMES = 6

    def save_roll_balance(self):
        """Keep the dye balance measured on this roll, to reuse it on short rolls or single frames of the
        same film scanned on the same set-up (a balance estimated on one frame alone is much less reliable)."""
        if self.engine != "scientific":
            QMessageBox.information(self, "Film profile", "The roll balance belongs to the Scientific engine.")
            return
        stats = [s for s in (self.stats_for(item) for item in self.items) if s is not None and not s.mono]
        if len(stats) < self.MIN_BALANCE_FRAMES:
            QMessageBox.information(
                self, "Film profile", f"A reliable balance needs at least {self.MIN_BALANCE_FRAMES} colour frames "
                                      f"with varied subjects (this roll has {len(stats)}).")
            return
        slopes = sc.roll_model(stats, None, self.base_reference).slopes      # the roll's own, without a profile
        film = self.session_info.get("film", "") if isinstance(self.session_info, dict) else ""
        default = f"{film or 'Film'} balance {datetime.now():%Y-%m-%d}"
        name, ok = QInputDialog.getText(
            self, "Film profile", f"Dye balance of this roll ({len(stats)} frames): R {slopes[0]:.3f}  G 1.000  "
                                  f"B {slopes[2]:.3f}\nName (film + light source):", text=default)
        if not ok or not name.strip():
            return
        profile = fp.FilmProfile(name=name.strip(), matrix=np.eye(3).tolist(),
                                 slopes=[round(float(v), 6) for v in slopes], gamma=sc.FILM_GAMMA,
                                 chart=f"roll balance ({len(stats)} frames)",
                                 source=Path(self.items[0].path).parent.name)
        path = self.film_profile_dir() / (fp_safe_name(profile.name) + ".json")
        try:
            profile.save(path)
        except OSError as error:
            QMessageBox.warning(self, "Film profile", f"Unable to save the profile: {error}")
            return
        self.statusBar().showMessage(f"Roll balance saved: {path}  (FILM → Load film profile… to use it on another roll)", 10000)

    def choose_film_profile(self):
        start = str(self.film_profile_dir()) if self.film_profile_dir().is_dir() else ""
        filename, _ = QFileDialog.getOpenFileName(self, "Film profile", start, "SMneg film profile (*.json)")
        if filename:
            self.set_film_profile(filename)

    def set_film_profile(self, path, quiet=False) -> bool:
        """Load (empty path: remove) the film profile. It acts at render time: nothing is re-read."""
        profile = None
        if path:
            try:
                profile = fp.load_film_profile(path)
            except (OSError, ValueError) as error:
                message = f"Film profile not loaded ({Path(path).name}): {error}"
                self.statusBar().showMessage(message, 15000) if quiet else QMessageBox.warning(self, "Film profile", message)
                path, profile = "", None
        self.film_profile, self.film_profile_path = profile, str(path or "")
        self._roll_cache = None
        self._log_cache.clear()
        self.zoom_cache = None
        self.btn_film.setText(f"FILM: {profile.name[:22]}" if profile else "FILM: auto")
        if profile:
            detail = (f"Chart ΔE00 {profile.delta_e_before} → {profile.delta_e_after}"
                      if profile.delta_e_after is not None else profile.chart)
            self.btn_film.setToolTip(f"{path}\n{detail} · gamma {profile.gamma}")
        if not quiet:
            self.persist_project()
            if self.items:
                self.refresh_current_view()
            if profile and self.engine != "scientific":
                self.statusBar().showMessage("The film profile is used by the Scientific engine.", 6000)
        return True

    # ==========================================================================
    # FILM BASE REFERENCE (scans of clear film, e.g. the roll's leader)
    # ==========================================================================
    def choose_base_reference(self):
        filenames, _ = QFileDialog.getOpenFileNames(
            self, "Scans of clear film (1 to 3, same camera exposure as the roll)", str(self.flat_path.parent)
            if self.flat_path else "", "Scans (" + " ".join(f"*{ext}" for ext in SUPPORTED_EXTS) + ")")
        if filenames:
            self.set_base_reference(filenames[:3])

    def set_base_reference(self, paths, base=None, quiet=False) -> bool:
        """Measure the film base on scans of clear film and use it for the whole roll (None: remove).
        ``base`` restores a saved measurement without re-reading the files."""
        if paths is None:
            self.base_reference, self.base_reference_files = None, []
        else:
            if base is None:
                scans = []
                for path in paths:
                    values = self.load_scan(path) if self.engine == "scientific" else sc.load_linear(
                        path, False, self.flat_gain if Path(path).suffix.lower() in RAW_EXTENSIONS else None)
                    if values is None:
                        QMessageBox.warning(self, "Film base", f"Unable to read {Path(path).name}: {self.load_error(path)}")
                        return False
                    scans.append(values)
                try:
                    base, spread, orange = sc.measure_film_base(scans)
                except ValueError as error:
                    QMessageBox.warning(self, "Film base", str(error))
                    return False
                problems = []
                if spread > 0.08:
                    problems.append("the scans are not uniform (picture or holder inside?)")
                if orange > sc.ORANGE_MASK:
                    problems.append("there is no orange mask (bare light, or B&W film?)")
                if problems and not quiet and QMessageBox.question(
                        self, "Film base", "Check the scans: " + "; ".join(problems) + ".\nUse them anyway?") \
                        != QMessageBox.StandardButton.Yes:
                    return False
            self.base_reference = np.asarray(base, np.float32)
            self.base_reference_files = [str(p) for p in paths]
        self._roll_cache = None
        self._log_cache.clear()
        self.zoom_cache = None
        if not quiet:
            self.persist_project()
            if self.items:
                self.refresh_current_view()
            self.statusBar().showMessage(
                "Film base reference: " + (", ".join(Path(p).name for p in self.base_reference_files)
                                           if self.base_reference is not None else "removed (automatic)"), 8000)
        return True

    def base_reference_data(self):
        if self.base_reference is None:
            return None
        return {"files": self.base_reference_files, "base": [float(v) for v in self.base_reference]}

    def clear_base_pick(self):
        item = self.current_item()
        if item is None or item.base_pick is None:
            return
        self.begin_edit()
        item.base_pick = None
        self.refresh_current_view()
        self.statusBar().showMessage("Film base: automatic detection", 4000)

    def reload_previews(self) -> bool:
        """Re-read every frame for the current engine (preview size). False if cancelled or failed."""
        self.zoom_cache = None
        self.zoom_base = None
        self._log_cache.clear()
        self._roll_cache = None
        if not self.items:
            return True
        dialog = QProgressDialog("Re-reading negatives…", "Cancel", 0, len(self.items), self)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        loaded = []
        for i, item in enumerate(self.items):
            dialog.setValue(i)
            if dialog.wasCanceled():
                dialog.close()
                return False
            base, stats = self.load_preview(item.path)
            if base is None:
                dialog.close()
                QMessageBox.warning(self, "Engine", f"Unable to read {Path(item.path).name}: {self.load_error(item.path)}")
                return False
            loaded.append((item, base, stats))
        dialog.close()
        for item, base, stats in loaded:
            item.base_positive, item.stats = base, stats
        return True

    # ==========================================================================
    # UNDO / REDO  (a snapshot of the frame is taken before each edit)
    # ==========================================================================
    HISTORY_LIMIT = 200

    @staticmethod
    def snapshot(item):
        return {key: getattr(item, key) for key in FRAME_FIELDS}

    def clear_history(self):
        # called from set_flat_field and on session change: the zoom cache is cleared as well
        self.zoom_cache = None
        self.zoom_base = None
        self._log_cache.clear()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.last_edit = None

    def push_undo(self, item, snapshot):
        self.push_undo_group([(item, snapshot)])

    def push_undo_group(self, entries):
        """One undo step that restores several frames at once (e.g. HOLD applied to the following frames)."""
        if not entries:
            return
        self.undo_stack.append(list(entries))
        del self.undo_stack[:-self.HISTORY_LIMIT]
        self.redo_stack.clear()

    def begin_edit(self, kind=None):
        """Records the state before an edit. Consecutive edits of the same kind (within one second) become a single step."""
        item = self.current_item()
        if item is None:
            return
        now = time.monotonic()
        last = self.last_edit
        self.last_edit = (kind, item, now)
        if kind and last and last[0] == kind and last[1] is item and now - last[2] < 1.0:
            return
        self.push_undo(item, self.snapshot(item))

    def step_history(self, source, target, label):
        self.last_edit = None
        while source:
            entries = []
            for item, saved in source.pop():
                index = next((i for i, other in enumerate(self.items) if other is item), None)
                if index is not None:
                    entries.append((index, item, saved))
            if not entries:
                continue
            target.append([(item, self.snapshot(item)) for _, item, _ in entries])
            for _, item, saved in entries:
                for key, value in saved.items():
                    setattr(item, key, value)
            index = entries[0][0]
            self.current_idx = index
            self.current_page = index // self.PAGE_SIZE
            self.refresh_current_view()
            self.statusBar().showMessage(f"{label} · frame #{index + 1:02d}", 3000)
            return True
        self.statusBar().showMessage(f"Nothing to {label.lower()}", 2000)
        return False

    def undo(self):
        self.step_history(self.undo_stack, self.redo_stack, "Undo")

    def redo(self):
        self.step_history(self.redo_stack, self.undo_stack, "Redo")

    def update_info_bar(self):
        item = self.current_item()
        if item is None:
            self.lbl_info.setText("")
            return
        crop = "Manual crop" if item.manual_crop else ("Auto-crop" if item.auto_crop else "No crop")
        parts = [
            f"#{item.index + 1:02d} {Path(item.path).name}",
            f"C{item.cyan:+d} M{item.magenta:+d} Y{item.yellow:+d} D{item.density:+d}",
            f"Contrast {item.contrast:.2f}", f"Sat {item.saturation:.2f}",
            f"Sharp {item.sharpness}", item.tone_profile, crop,
        ]
        if self.engine == "scientific" and item.stats is not None:
            stats = self.stats_for(item)
            if stats.source in ("rebate", "picked") or stats.mono:
                origin = stats.source
            elif self.base_reference is not None:
                origin = "reference"
            else:
                roll = self.roll()
                origin = f"{stats.source} → roll" if roll is None or not np.allclose(roll.base, stats.base) else stats.source
            parts.append(f"Base: {origin}" + (" · B&W" if stats.mono else ""))
            parts.append("Auto print" if item.auto_print else "Flat master")
            if item.grey_picks:
                parts.append(f"Grey picks: {len(item.grey_picks)}")
            if self.camera_profile is not None:
                parts.append(f"Profile: {self.camera_profile.name}")
            if self.film_profile is not None:
                parts.append(f"Film: {self.film_profile.name}")
        else:
            parts.append(ENGINE_LABELS[self.engine])
        if item.straighten:
            parts.append(f"Straightened {item.straighten:+.1f}°")
        if item.show_clipping:
            parts.append("CLIPPING")
        if self.held_settings:
            parts.append("HOLD ON")
        parts.append(f"Undo {len(self.undo_stack)}")
        self.lbl_info.setText("  ·  ".join(parts))

    def toggle_view(self):
        if self.stack.currentIndex() == 0:
            if self.items:
                self.switch_to_large_view()
        else:
            self.switch_to_grid_view()

    def cycle_tone_profile(self):
        if self.current_item() is None:
            return
        index = (self.tone_profile.currentIndex() + 1) % self.tone_profile.count()
        self.tone_profile.setCurrentIndex(index)
        self.change_tone_profile(index)

    def render_frame_16bit(self, item, base_positive):  # Classic engine
        # same pipeline but fully in float, outputs uint16 (for TIFF export)
        rendered = OfficialFilmEngine.apply_pipeline(
            base_positive=base_positive,
            cyan_points=item.cyan,
            magenta_points=item.magenta,
            yellow_points=item.yellow,
            density_step=item.density,
            contrast=item.contrast,
            saturation=item.saturation,
            rotation=item.rotation,
            mirror=item.mirror,
            auto_crop=item.auto_crop and item.manual_crop is None,
            show_clipping=False,
            output_float=True,
        )
        if item.tone_profile != "Natural":
            rendered = tone_curve(rendered, item.tone_profile).astype(np.float32)
        rendered = straighten_image(rendered, item.straighten)
        rendered = self.sharpen(rendered, item.sharpness)
        rendered = apply_crop(rendered, item.manual_crop)
        return np.rint(np.clip(rendered, 0.0, 1.0) * 65535.0).astype(np.uint16)

    def load_error(self, path):
        return OfficialFilmEngine.errors.get(path, "unreadable file")

    def change_tone_profile(self, index):
        item = self.current_item()
        if item is not None:
            self.begin_edit()
            item.tone_profile = self.tone_profile.itemText(index)
            self.refresh_current_view()

    def sync_tone_profile(self):
        item = self.current_item()
        self.tone_profile.setEnabled(item is not None)
        self.tone_profile.setCurrentText(item.tone_profile if item else "Natural")
        on = item is None or item.auto_print
        self.btn_auto_print.setText("AUTO PRINT [L]" if on else "FLAT MASTER [L]")
        self.btn_auto_print.setStyleSheet(
            f"background-color: {'#00695C' if on else '#424242'}; color: white; border: 1px solid #111; "
            "padding: 6px 10px; border-radius: 3px;")

    def toggle_auto_print(self):
        item = self.current_item()
        if item is None:
            return
        self.begin_edit()
        item.auto_print = not item.auto_print
        self.refresh_current_view()
        if self.engine != "scientific":
            self.statusBar().showMessage("Auto print is part of the Scientific engine.", 4000)

    def reset_frame(self):
        item = self.current_item()
        if item is None:
            return
        self.begin_edit()
        fresh = FrameItem(
            index=item.index, path=item.path, base_positive=item.base_positive,
            processed_date=item.processed_date,
        )
        for key in FRAME_FIELDS:
            setattr(item, key, getattr(fresh, key))
        self.refresh_current_view()

    def open_sharpness(self):
        item = self.current_item()
        if item is None:
            return

        original = item.sharpness
        snapshot = self.snapshot(item)
        dialog = QDialog(self)
        dialog.setWindowTitle("Sharpness")
        layout = QVBoxLayout(dialog)
        label = QLabel(f"Sharpness · {original}")
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(original)

        def update_sharpness(value):
            item.sharpness = value
            label.setText(f"Sharpness · {value}")
            self.refresh_current_view()

        slider.valueChanged.connect(update_sharpness)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(label)
        layout.addWidget(slider)
        layout.addWidget(buttons)
        if not dialog.exec():
            update_sharpness(original)
        elif item.sharpness != original:
            self.push_undo(item, snapshot)

    def open_manual_crop(self):
        item = self.current_item()
        if item is None:
            return
        preview = self.render_frame(item, item.base_positive, edit_crop=True)
        bounds = item.manual_crop
        if bounds is None and item.auto_crop:
            height, width = preview.shape[:2]
            bounds = (
                int(width * 0.05) / width,
                int(height * 0.05) / height,
                int(width * 0.95) / width,
                int(height * 0.95) / height,
            )
        dialog = ManualCropDialog(preview, bounds, self, angle=item.straighten)
        if dialog.exec():
            self.push_undo(item, self.snapshot(item))
            item.manual_crop = dialog.crop
            item.straighten = dialog.angle.value()
            item.auto_crop = False
            self.refresh_current_view()

    def load_scan(self, path, full_resolution=False, flat_field=_DEFAULT):
        """Classic: normalized inverted base. Scientific: linear scan values (inversion happens at render)."""
        gain = self.flat_gain if flat_field is _DEFAULT else flat_field
        gain = gain if Path(path).suffix.lower() in RAW_EXTENSIONS else None
        if self.engine == "scientific":
            return sc.load_linear(path, full_resolution, gain)
        return OfficialFilmEngine.load_negative_base(path, full_resolution, gain)

    def load_preview(self, path, flat_field=_DEFAULT):
        """Preview data and (scientific engine) its film statistics. Safe to call from worker threads."""
        base = self.load_scan(path, False, flat_field)
        stats = sc.frame_stats(base) if base is not None and self.engine == "scientific" else None
        return base, stats

    def update_flat_button(self):
        self.btn_flat.setText("FLAT FIELD · ON" if self.flat_gain is not None else "FLAT FIELD")
        self.btn_flat.setToolTip(str(self.flat_path) if self.flat_path else "RAW reference of the diffuser without film")

    def restore_flat_field(self, saved):
        self.flat_path = Path(saved).resolve() if saved else None
        self.flat_gain = None
        if self.flat_path:
            try:
                self.flat_gain = build_flat_field(decode_negative(str(self.flat_path), False))
            except (ValueError, OSError, RuntimeError, LibRawError, cv2.error) as error:
                self.statusBar().showMessage(f"Flat field unavailable: {error}", 15000)
        self.update_flat_button()

    def choose_flat_field(self):
        item = self.current_item()
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Flat Field")
        if self.flat_path:
            dialog.setText(f"Active reference: {self.flat_path.name}")
        else:
            dialog.setText("Choose the RAW scan of the light source without film.")
        use_selected = dialog.addButton("Use the selected frame", QMessageBox.ButtonRole.AcceptRole)
        use_selected.setEnabled(item is not None and Path(item.path).suffix.lower() in RAW_EXTENSIONS)
        browse = dialog.addButton("Choose a file…", QMessageBox.ButtonRole.ActionRole)
        disable = None
        if self.flat_path:
            disable = dialog.addButton("Disable", QMessageBox.ButtonRole.ActionRole)
        dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.exec()
        clicked = dialog.clickedButton()
        if clicked == use_selected and item is not None:
            self.set_flat_field(Path(item.path))
            return
        if disable is not None and clicked == disable:
            self.set_flat_field(None)
            return
        if clicked != browse:
            return

        filename, _ = QFileDialog.getOpenFileName(
            self, "Flat-field reference (diffuser without film)",
            str(self.flat_path.parent) if self.flat_path else "",
            "RAW (" + " ".join(f"*{ext} *{ext.upper()}" for ext in sorted(RAW_EXTENSIONS)) + ")",
        )
        if filename:
            self.set_flat_field(Path(filename).resolve())

    def set_flat_field(self, reference):
        if reference is not None:
            reference = reference.resolve()
        try:
            if reference is not None and reference.suffix.lower() not in RAW_EXTENSIONS:
                raise ValueError("Select a RAW reference.")
            gain = build_flat_field(decode_negative(str(reference), False)) if reference is not None else None
            frames = [
                item for item in self.items
                if reference is None or Path(item.path).resolve() != reference
            ]
            updated = []
            for item in frames:
                if Path(item.path).suffix.lower() in RAW_EXTENSIONS:
                    base, stats = self.load_preview(item.path, flat_field=gain)
                    if base is None:
                        raise ValueError(f"Unable to recompute {Path(item.path).name}.")
                    updated.append((item, base, stats))
        except (ValueError, OSError, RuntimeError, LibRawError, cv2.error) as error:
            QMessageBox.warning(self, "Flat Field", str(error))
            return

        for item, base, stats in updated:
            item.base_positive, item.stats = base, stats
        self._log_cache.clear()
        selected = self.current_item()
        if selected is not None:
            self.current_idx = next(
                (index for index, item in enumerate(frames) if item is selected),
                min(self.current_idx, max(0, len(frames) - 1)),
            )
        self.clear_history()
        self.items = frames
        for index, item in enumerate(self.items):
            item.index = index
        self.current_page = self.current_idx // self.PAGE_SIZE
        self.lbl_count.setText(f"{len(self.items)} FRAMES")
        if not self.items:
            self.switch_to_grid_view()
        self.flat_path, self.flat_gain = reference, gain
        app_settings().setValue("flat_field_reference", str(reference) if reference else "")
        self.update_flat_button()
        self.refresh_current_view()

    def open_original(self):
        item = self.current_item()
        if item is None:
            return
        try:
            values = decode_negative(item.path, full_resolution=False)
        except (OSError, ValueError, RuntimeError, LibRawError, cv2.error) as error:
            QMessageBox.warning(self, "Original", f"Unable to open the source file: {error}")
            return
        if Path(item.path).suffix.lower() in RAW_EXTENSIONS:
            values = np.power(np.clip(values, 0, 1), 1 / 2.2)
        image = (np.clip(values, 0, 1) * 255).astype(np.uint8)
        dialog = ZoomDialog(image, Path(item.path).name, self)
        dialog.setWindowTitle(f"Original before inversion — {Path(item.path).name}")
        dialog.exec()

    # ==========================================================================
    # In-place ZOOM (wheel / drag / Z). The full-size image loads in a background thread
    # ==========================================================================
    def open_zoom(self):
        """Z: toggle between fit and 100% in the same enlarged view."""
        if self.current_item() is None:
            return
        if self.stack.currentIndex() == 0:
            self.switch_to_large_view(self.current_idx)
        canvas = self.large_preview.canvas
        if canvas.is_zoomed():
            canvas.reset_fit()
            return
        self.begin_zoom()
        local = canvas.mapFromGlobal(QCursor.pos())
        canvas.zoom_to_100(QPointF(local) if canvas.rect().contains(local) else None)

    def begin_zoom(self):
        item = self.current_item()
        if item is None or self.zoom_item is item:
            return
        self.zoom_item = item
        cache, self.zoom_cache = self.zoom_cache, None
        reusable = cache is not None and cache[0] is item and cache[1] is self.flat_gain
        self.zoom_base = cache[2] if reusable else None
        edge = source_max_edge(item.path)
        preview_edge = max(item.base_positive.shape[:2])
        self.large_preview.canvas.set_full_ratio(edge / preview_edge if edge else 3.0)
        self.zoom_version += 1
        self.start_zoom_job()

    def end_zoom(self):
        if self.zoom_item is not None:
            if self.zoom_future is not None:
                self.statusBar().clearMessage()
            if self.zoom_base is not None:   # kept so the next zoom on the same frame is instant
                self.zoom_cache = (self.zoom_item, self.flat_gain, self.zoom_base)
        self.zoom_item = None
        self.zoom_base = None
        self.zoom_version += 1
        self.zoom_refresh_timer.stop()

    def schedule_zoom_refresh(self):
        self.zoom_version += 1
        self.zoom_refresh_timer.start()

    def start_zoom_job(self):
        item = self.zoom_item
        if item is None or self.zoom_future is not None:
            return
        version = self.zoom_version
        snapshot = copy.copy(item)
        base = self.zoom_base
        params = self.frame_params(item) if self.engine == "scientific" else None

        def job():
            full = base if base is not None else self.load_scan(snapshot.path, full_resolution=True)
            if full is None:
                return item, version, None, None, self.load_error(snapshot.path)
            rendered = np.ascontiguousarray(
                self.render_frame(snapshot, full, show_clipping=snapshot.show_clipping, params=params))
            if snapshot.is_passed:
                mark_passed(rendered)
            return item, version, full, cv2.cvtColor(rendered, cv2.COLOR_RGB2BGRA), None

        self.zoom_future = self.zoom_worker.submit(job)
        self.statusBar().showMessage("Loading full resolution…")
        self.zoom_timer.start()

    def poll_zoom_job(self):
        future = self.zoom_future
        if future is None:
            self.zoom_timer.stop()
            return
        if not future.done():
            return
        self.zoom_timer.stop()
        self.zoom_future = None
        try:
            item, version, full, image, reason = future.result()
        except Exception as exc:
            self.statusBar().showMessage(f"Zoom unavailable: {exc}", 10000)
            return
        if item is not self.zoom_item:
            return
        if full is None:
            self.statusBar().showMessage(f"Full resolution unavailable: {reason}", 10000)
            return
        self.zoom_base = full
        if version != self.zoom_version:
            self.start_zoom_job()
            return
        self.large_preview.canvas.set_full_bgra(image)
        self.statusBar().clearMessage()

    def persist_project(self):
        if self.session_folder is None:
            return save_session(self.items, self.current_idx, self.stack.currentIndex(),
                                str(self.flat_path or ""), self.session_info, self.engine,
                                self.camera_profile_path, self.film_profile_path, self.base_reference_data(), self.meter)
        try:
            write_project(self.session_folder, self.items, self.current_idx,
                          self.stack.currentIndex(), self.camera_reference, str(self.flat_path or ""),
                          self.session_info, self.engine, self.camera_profile_path, self.film_profile_path, self.base_reference_data(), self.meter)
        except OSError as error:
            self.statusBar().showMessage(f"Session not saved: {error}", 15000)
            return False
        return True

    def edit_session_info(self):
        dialog = SessionInfoDialog(self, self.session_info)
        if dialog.exec():
            self.session_info = dialog.info()
            self.persist_project()

    def new_session(self):
        settings = app_settings()
        dialog = SessionInfoDialog(self, {}, "New session · information")
        if not dialog.exec():
            return
        info = dialog.info()
        parent = QFileDialog.getExistingDirectory(
            self, "Parent folder for sessions", settings.value("session_parent", "", type=str),
        )
        if not parent:
            return
        if not self.persist_project():
            return
        try:
            folder = create_session_folder(Path(parent).resolve())
            write_project(folder, [], 0, 0, {}, str(self.flat_path or ""), info, self.engine,
                          self.camera_profile_path, self.film_profile_path)      # a new roll: no base reference yet
        except OSError as error:
            QMessageBox.warning(self, "Session", str(error))
            return
        settings.setValue("session_parent", parent)
        self.activate_project(folder, {"flat_field_reference": str(self.flat_path or ""), "session_info": info,
                                       "engine": self.engine, "camera_profile": self.camera_profile_path,
                                       "film_profile": self.film_profile_path})

    def apply_session_engine(self, data):
        """Sessions saved before the scientific engine existed keep the Classic look."""
        engine = data.get("engine") or ("classic" if data.get("frames") else self.engine)
        self.engine = engine if engine in ENGINES else "classic"
        self._roll_cache = None
        self._log_cache.clear()
        self.sync_engine_box()
        saved = data.get("camera_profile")
        if saved is None:   # sessions without the field: keep the profile last used in the app
            saved = app_settings().value("camera_profile", "", type=str)
        self.set_camera_profile(saved, quiet=True)
        self.set_film_profile(data.get("film_profile", ""), quiet=True)
        self.set_meter(data.get("meter") or self.meter, quiet=True)
        saved = data.get("film_base_reference")
        if saved:
            self.set_base_reference(saved.get("files", []), base=saved.get("base"), quiet=True)
        else:
            self.set_base_reference(None, quiet=True)

    # ==========================================================================
    # CAMERA PROFILE (IT8 transparency target: camera + light source colours)
    # ==========================================================================
    def choose_camera_profile(self):
        start = str(Path(self.camera_profile_path).parent) if self.camera_profile_path else ""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Camera profile (IT8 report from it8_profiler)", start, "IT8 profile (*.json)")
        if filename:
            self.set_camera_profile(filename)

    def set_camera_profile(self, path, quiet=False) -> bool:
        """Load (or, with an empty path, remove) the camera profile. Applies to the Scientific engine."""
        profile = None
        if path:
            try:
                profile = sc.load_camera_profile(path)
            except (OSError, ValueError) as error:
                message = f"Camera profile not loaded ({Path(path).name}): {error}"
                if quiet:
                    self.statusBar().showMessage(message, 15000)
                else:
                    QMessageBox.warning(self, "Camera profile", message)
                path, profile = "", None
        self.camera_profile, self.camera_profile_path = profile, str(path or "")
        self._camera_matrix = profile.working_matrix() if profile else None
        self.btn_profile.setText(f"CAMERA: {profile.name[:20]}" if profile else "CAMERA: none")
        tip = "Colour profile of the camera + light source, measured on an IT8 transparency target."
        if profile:
            tip += f"\n{path}" + (f"\nAccuracy on the target: mean ΔE00 {profile.mean_de00:.2f}"
                                    if profile.mean_de00 else "")
        self.btn_profile.setToolTip(tip)
        if not quiet:
            app_settings().setValue("camera_profile", self.camera_profile_path)
            self.zoom_cache = None
            self.persist_project()
            if self.items:
                self.refresh_current_view()
            if profile and self.engine != "scientific":
                self.statusBar().showMessage("The camera profile is used by the Scientific engine.", 6000)
        return profile is not None or not path

    def activate_project(self, folder, data):
        self.session_timer.stop()
        self.apply_session_engine(data)
        self.session_folder = folder
        self.camera_reference = data.get("camera_reference", {})
        self.session_info = data.get("session_info", {})
        settings = app_settings()
        reference = data.get("flat_field_reference")
        if reference is None:
            legacy = settings.value("flat_field_reference", "", type=str)
            if legacy and Path(legacy).resolve().parent == folder.resolve():
                reference = legacy
        self.restore_flat_field(reference)
        self.clear_history()
        self.items = []
        self.current_idx = self.current_page = 0
        self.stack.setCurrentIndex(0)
        self.setWindowTitle(f"SMneg | {folder.name}")
        self.btn_session.setToolTip(str(folder))
        settings.setValue("active_project", str(folder))
        settings.sync()
        self.restore_frames(data)
        self.watch_session_action.setEnabled(True)
        self.start_hot_folder(folder)

    def record_camera_reference(self, path):
        current = read_camera_reference(path)
        if self.camera_reference:
            differences = camera_differences(self.camera_reference, current)
        else:
            settings = app_settings()
            previous = settings.value("camera_reference", {})
            differences = camera_differences(previous or {}, current)
            self.camera_reference = current
            if len(current) > 1:
                settings.setValue("camera_reference", current)
        if differences:
            self.statusBar().showMessage(
                f"Settings differ from the reference ({Path(path).name}): {', '.join(differences)}", 15000,
            )
        elif len(current) == 1:
            self.statusBar().showMessage(f"Camera settings unavailable: {Path(path).name}", 10000)

    def show_shortcuts(self):
        ShortcutsDialog(self).exec()

    def shutdown_workers(self):
        self.zoom_timer.stop()
        self.zoom_refresh_timer.stop()
        self.restore_worker.shutdown(wait=False, cancel_futures=True)
        self.zoom_worker.shutdown(wait=False, cancel_futures=True)

    def closeEvent(self, event):
        if self.restoring_frames:
            self.restoring_frames = False
            self.shutdown_workers()
            super().closeEvent(event)
            return
        saved = self.persist_project()
        if not saved:
            choice = QMessageBox.warning(
                self, "Session not saved", "Close without saving the session?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if choice != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.shutdown_workers()
        super().closeEvent(event)

    def restore_startup(self):
        self.restore_session()

    def restore_session(self):
        if self.items:
            return
        settings = app_settings()
        folder = settings.value("active_project", "", type=str)
        if folder:
            try:
                project = read_project(Path(folder))
            except (OSError, ValueError) as error:
                self.statusBar().showMessage(f"Session unavailable: {error}", 15000)
            else:
                self.activate_project(Path(folder), project)
                return
        data = load_session()
        self.apply_session_engine(data)
        self.session_info = data.get("session_info", {})
        self.restore_flat_field(data.get("flat_field_reference"))
        self.restore_frames(data)

    def restore_frames(self, session):
        frames = session.get("frames", [])
        if not frames:
            self.lbl_count.setText("0 FRAMES")
            self.refresh_current_view()
            return

        selected = min(max(session.get("current_idx", 0), 0), len(frames) - 1)
        selected_path = frames[selected]["path"]
        pending = iter(enumerate(frames, start=1))
        decoding = deque()
        missing = 0
        missing_names = []
        restored_selection = 0
        self.restoring_frames = True
        self.centralWidget().setEnabled(False)
        self.statusBar().showMessage(f"Restoring session · 0/{len(frames)}")

        def restore_next():
            if not self.restoring_frames:
                return
            while len(decoding) < self.RESTORE_WORKERS:
                entry = next(pending, None)
                if entry is None:
                    break
                index, frame = entry
                path = frame["path"]
                is_reference = self.flat_path and Path(path).resolve() == self.flat_path
                future = None if is_reference else self.restore_worker.submit(self.load_preview, path)
                decoding.append((index, frame, future))

            if not decoding:
                self.restoring_frames = False
                self.centralWidget().setEnabled(True)
                self.current_idx = restored_selection
                self.current_page = self.current_idx // self.PAGE_SIZE
                self.lbl_count.setText(f"{len(self.items)} FRAMES")
                if self.items and session.get("view") == 1:
                    self.stack.setCurrentIndex(1)
                self.refresh_current_view()
                if missing:
                    names = ", ".join(missing_names[:3]) + (" …" if len(missing_names) > 3 else "")
                    self.statusBar().showMessage(f"{missing} session file(s) unavailable: {names}", 20000)
                else:
                    self.statusBar().clearMessage()
                return

            index, frame, future = decoding[0]
            if future is not None and not future.done():
                QTimer.singleShot(30, self, restore_next)
                return
            decoding.popleft()
            finish_frame(index, frame, future.result() if future is not None else None)

        def finish_frame(index, frame, loaded):
            nonlocal missing, restored_selection
            base, stats = loaded if loaded is not None else (None, None)
            if base is not None:
                item = FrameItem(index=len(self.items), path=frame["path"], base_positive=base, stats=stats)
                for key in FRAME_FIELDS:
                    if key in frame:
                        setattr(item, key, frame[key])
                self.items.append(item)
                self.lbl_count.setText(f"{len(self.items)} FRAMES")
                if item.index < self.PAGE_SIZE:
                    self.refresh_current_view()
                if item.path == selected_path:
                    restored_selection = item.index
            else:
                missing += 1
                missing_names.append(Path(frame["path"]).name)
            self.statusBar().showMessage(f"Restoring session · {index}/{len(frames)}")
            QTimer.singleShot(0, self, restore_next)

        QTimer.singleShot(0, self, restore_next)

    def capture_image(self):
        if sys.platform != "darwin":
            QMessageBox.warning(self, "Capture", "The NX Tether command is only available on macOS.")
            return
        if self.hot_folder is None:
            QMessageBox.warning(self, "Capture", "Enable the Hot Folder and select the NX Tether destination.")
            return
        if self.capture_process.state() != QProcess.ProcessState.NotRunning:
            return
        self.btn_capture.setEnabled(False)
        self.statusBar().showMessage("Triggering Nikon NX Tether…")
        self.opening_tether = True
        self.capture_process.start("/usr/bin/open", ["-a", NX_TETHER_PATH])

    def capture_finished(self, exit_code, exit_status):
        if self.opening_tether:
            self.opening_tether = False
            if exit_code == 0 and exit_status == QProcess.ExitStatus.NormalExit:
                self.capture_process.start("/usr/bin/osascript", ["-l", "JavaScript", "-e", CAPTURE_SCRIPT])
                return
        self.btn_capture.setEnabled(True)
        if exit_code == 0 and exit_status == QProcess.ExitStatus.NormalExit:
            self.statusBar().showMessage(
                f"Command sent. Waiting for an image in {self.hot_folder.directory}."
                if self.hot_folder else "Command sent. Hot Folder stopped.",
                12000,
            )
        else:
            details = bytes(self.capture_process.readAllStandardError()).decode(errors="replace").strip()
            if ACCESSIBILITY_REQUIRED in details or "(1002)" in details:
                self.show_capture_permissions()
                return
            QMessageBox.warning(
                self, "Capture NX Tether",
                f"Check NX Tether, the Shoot shortcut {SHOOT_SHORTCUT} and the macOS permissions.\n{details}",
            )

    def show_capture_permissions(self):
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Capture permission")
        dialog.setText("macOS requires Accessibility access to send ⌘K to NX Tether.")
        dialog.setInformativeText(
            "If the system prompt does not appear, open the settings below. "
            "Allow the application named by macOS, then click CAPTURE again."
        )
        settings = dialog.addButton("Open Accessibility settings", QMessageBox.ButtonRole.ActionRole)
        dialog.addButton(QMessageBox.StandardButton.Close)
        dialog.exec()
        if dialog.clickedButton() == settings:
            QDesktopServices.openUrl(QUrl(ACCESSIBILITY_SETTINGS))

    def capture_process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.opening_tether = False
            self.btn_capture.setEnabled(True)
            QMessageBox.warning(self, "Capture", self.capture_process.errorString())

    def stop_hot_folder(self):
        self.hot_timer.stop()
        self.hot_folder = None
        self.btn_hot_folder.setText("HOT FOLDER")
        self.btn_hot_folder.setToolTip("")
        self.stop_hot_action.setEnabled(False)
        self.lbl_feed.setText("Semi Mode")

    def watch_session_folder(self):
        if self.session_folder is not None:
            self.start_hot_folder(self.session_folder)

    def choose_hot_folder(self):
        settings = app_settings()
        previous = settings.value("hot_folder", "", type=str)
        folder = QFileDialog.getExistingDirectory(self, "Watched folder (Nikon)", previous)
        if folder:
            settings.setValue("hot_folder", folder)
            self.start_hot_folder(Path(folder))

    def start_hot_folder(self, folder):
        folder = folder.resolve()
        self.hot_folder = HotFolder(folder, SUPPORTED_EXTS)
        self.failed_imports = set()
        self.btn_hot_folder.setText("HOT FOLDER · ON")
        self.btn_hot_folder.setToolTip(str(folder))
        self.stop_hot_action.setEnabled(True)
        self.lbl_feed.setText("Hot Folder")
        if not self.restoring_frames:
            self.statusBar().showMessage(f"Watching folder: {folder}")
        self.import_hot_folder()
        self.hot_timer.start()

    def import_hot_folder(self):
        if self.restoring_frames or self.hot_folder is None or QApplication.activeModalWidget() is not None:
            return
        try:
            ready = self.hot_folder.ready_files()
        except OSError:
            self.btn_hot_folder.setToolTip(f"Folder unavailable: {self.hot_folder.directory}")
            return

        self.btn_hot_folder.setToolTip(str(self.hot_folder.directory))
        existing = {Path(item.path).resolve() for item in self.items}
        for path in ready:
            if path in existing or path in self.failed_imports:
                continue
            if not self.import_frame(str(path)):
                if not (self.flat_path and path == self.flat_path):
                    self.failed_imports.add(path)
                    self.statusBar().showMessage(f"Import failed: {path.name} — {self.load_error(str(path))}", 15000)
                continue
            self.current_idx = len(self.items) - 1
            self.current_page = self.current_idx // self.PAGE_SIZE
            self.lbl_count.setText(f"{len(self.items)} FRAMES")
            self.refresh_current_view()
            self.statusBar().showMessage(f"Imported: {path.name}", 5000)
            if self.session_folder is not None:
                self.record_camera_reference(path)
            break

    def import_frame(self, path: str) -> bool:
        if self.flat_path and Path(path).resolve() == self.flat_path:
            return False
        base, stats = self.load_preview(path)
        if base is None:
            return False
        self.items.append(FrameItem(index=len(self.items), path=path, base_positive=base, stats=stats))
        return True

    def select_roll_folder(self):
        settings = app_settings()
        last_folder = settings.value("last_roll_folder", "", type=str)
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select the negatives folder",
            last_folder if os.path.isdir(last_folder) else "",
        )
        if not folder:
            return

        settings.setValue("last_roll_folder", folder)
        project_folder = Path(folder).resolve()
        if project_path(project_folder).is_file():
            if not self.persist_project():
                return
            try:
                project = read_project(project_folder)
            except (OSError, ValueError) as error:
                QMessageBox.warning(self, "Session", str(error))
                return
            self.activate_project(project_folder, project)
            return
        if not self.persist_project():
            return
        self.session_timer.stop()

        files = sorted([
            os.path.join(folder, f) for f in os.listdir(folder)
            if f.lower().endswith(SUPPORTED_EXTS)
        ])

        if not files:
            QMessageBox.warning(self, "No files", "No compatible negatives found.")
            return

        dlg = QProgressDialog("Quick inversion of negatives...", "Cancel", 0, len(files), self)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)

        previous_reference = (self.base_reference, self.base_reference_files)
        self.set_base_reference(None, quiet=True)          # a new roll: the previous roll's base does not apply
        previous_items, self.items = self.items, []
        failed = []
        # previews decode in parallel (LibRaw and NumPy release the GIL); frames are added in file order
        with ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 1), thread_name_prefix="smneg-import") as pool:
            jobs = [(path, None if self.flat_path and Path(path).resolve() == self.flat_path
                     else pool.submit(self.load_preview, path)) for path in files]
            for i, (path, job) in enumerate(jobs):
                dlg.setValue(i)
                while job is not None and not job.done() and not dlg.wasCanceled():
                    QApplication.processEvents()
                    time.sleep(0.01)
                if dlg.wasCanceled():
                    for _, pending in jobs:
                        if pending is not None:
                            pending.cancel()
                    break
                if job is None:
                    continue
                base, stats = job.result()
                if base is None:
                    failed.append(f"{Path(path).name}: {self.load_error(path)}")
                    continue
                self.items.append(FrameItem(index=len(self.items), path=path, base_positive=base, stats=stats))

        cancelled = dlg.wasCanceled()
        dlg.close()
        if cancelled or not self.items:
            self.items = previous_items
            self.base_reference, self.base_reference_files = previous_reference
            self._roll_cache = None
            if failed and not cancelled:
                QMessageBox.warning(self, "Import", "No frame could be read:\n" + "\n".join(failed[:10]))
            return
        if failed:
            QMessageBox.warning(self, "Import", f"{len(failed)} file(s) could not be read:\n"
                                + "\n".join(failed[:10]) + ("\n…" if len(failed) > 10 else ""))
        self.session_timer.stop()
        self.session_folder = None
        self.camera_reference = {}
        self.current_page = self.current_idx = 0
        self.stack.setCurrentIndex(0)
        self.persist_project()
        settings.remove("active_project")
        settings.sync()
        self.watch_session_action.setEnabled(False)
        self.stop_hot_folder()
        self.setWindowTitle("SMneg | Film Negative Inversion")
        self.btn_session.setToolTip("")
        self.lbl_count.setText(f"{len(self.items)} FRAMES")
        self.current_page = 0
        self.current_idx = 0
        self.switch_to_grid_view()
        self.refresh_current_view()

    def refresh_current_view(self):
        if self.items and not self.restoring_frames:
            self.session_timer.start()
        total = len(self.items)
        if total > 0:
            start_num = self.current_page * self.PAGE_SIZE + 1
            end_num = min((self.current_page + 1) * self.PAGE_SIZE, total)
            self.lbl_batch_indicator.setText(f"Batch {self.current_page + 1} (Frames {start_num}-{end_num})")
        else:
            self.lbl_batch_indicator.setText("Batch 0 (0-0)")

        if self.stack.currentIndex() == 0:
            self.refresh_grid()
        else:
            self.update_large_view()
        self.update_info_bar()

    def refresh_grid(self):
        if self.zoom_cache is not None and self.zoom_cache[0] is not self.current_item():
            self.zoom_cache = None
        self.sync_tone_profile()
        start = self.current_page * self.PAGE_SIZE
        for s in range(self.PAGE_SIZE):
            idx = start + s
            card = self.cards[s]
            if idx < len(self.items):
                item = self.items[idx]
                card.setVisible(True)
                rendered = self.render_item(item)
                card.update_card(item, rendered)
                card.set_active(idx == self.current_idx)
            else:
                card.setVisible(True)
                card.update_card(None, None)
                card.set_active(False)

    def update_large_view(self):
        self.sync_tone_profile()
        item = self.current_item()
        if not item:
            return
        if self.zoom_item is not None and self.zoom_item is not item:
            self.large_preview.canvas.reset_fit()
            self.end_zoom()
        if self.zoom_cache is not None and self.zoom_cache[0] is not item:
            self.zoom_cache = None
        rendered = self.render_item(item)
        self.large_preview.update_view(item, rendered)
        if self.zoom_item is item:
            self.schedule_zoom_refresh()

    def switch_to_large_view(self, frame_index: Optional[int] = None):
        if frame_index is not None and 0 <= frame_index < len(self.items):
            self.current_idx = frame_index
            self.current_page = self.current_idx // self.PAGE_SIZE
        self.stack.setCurrentIndex(1)
        self.update_large_view()

    def switch_to_grid_view(self):
        self.large_preview.canvas.reset_fit()
        self.end_zoom()
        self.stack.setCurrentIndex(0)
        self.refresh_grid()

    def on_frame_click(self, frame_index: int):
        self.current_idx = frame_index
        self.refresh_grid()

    def current_item(self) -> Optional[FrameItem]:
        if 0 <= self.current_idx < len(self.items):
            return self.items[self.current_idx]
        return None

    def adjust_color(self, chan: str, delta: int):
        item = self.current_item()
        if not item:
            return
        self.begin_edit("color")
        if chan == "C":
            item.cyan = max(-50, min(50, item.cyan + delta))
        elif chan == "M":
            item.magenta = max(-50, min(50, item.magenta + delta))
        elif chan == "Y":
            item.yellow = max(-50, min(50, item.yellow + delta))
        self.refresh_current_view()

    def clear_color(self):
        item = self.current_item()
        if item:
            self.begin_edit()
            item.cyan = 0
            item.magenta = 0
            item.yellow = 0
            self.refresh_current_view()

    def adjust_density(self, delta: int):
        item = self.current_item()
        if item:
            self.begin_edit("density")
            item.density = max(-50, min(50, item.density + delta))
            self.refresh_current_view()

    def clear_density(self):
        item = self.current_item()
        if item:
            self.begin_edit()
            item.density = 0
            self.refresh_current_view()

    def adjust_contrast(self, delta: float):
        item = self.current_item()
        if item:
            self.begin_edit("contrast")
            item.contrast = max(0.5, min(2.0, round(item.contrast + delta, 2)))
            self.refresh_current_view()

    def adjust_saturation(self, delta: float):
        item = self.current_item()
        if item:
            self.begin_edit("saturation")
            item.saturation = max(0.0, min(2.0, round(item.saturation + delta, 2)))
            self.refresh_current_view()

    @staticmethod
    def set_orientation(item, rotation, mirror):
        """Change rotation / mirror and move the manual crop and the straighten angle with the picture content,
        so the crop keeps framing the same part of the scene."""
        rotation %= 360
        item.manual_crop, item.straighten = reorient(
            item.manual_crop, item.straighten, (item.rotation, item.mirror), (rotation, mirror))
        item.rotation, item.mirror = rotation, mirror

    def rotate_cw(self):
        item = self.current_item()
        if item:
            self.begin_edit()
            self.set_orientation(item, item.rotation + 90, item.mirror)
            self.refresh_current_view()

    def rotate_ccw(self):
        item = self.current_item()
        if item:
            self.begin_edit()
            self.set_orientation(item, item.rotation - 90, item.mirror)
            self.refresh_current_view()

    def toggle_mirror(self):
        item = self.current_item()
        if item:
            self.begin_edit()
            self.set_orientation(item, item.rotation, not item.mirror)
            self.refresh_current_view()

    def toggle_auto_crop(self):
        item = self.current_item()
        if item:
            self.begin_edit()
            if item.manual_crop is not None:
                item.manual_crop = None
                item.auto_crop = True
            else:
                item.auto_crop = not item.auto_crop
            self.refresh_current_view()

    def toggle_clipping(self):
        item = self.current_item()
        if item:
            item.show_clipping = not item.show_clipping
            self.refresh_current_view()

    def toggle_pass(self):
        item = self.current_item()
        if item:
            self.begin_edit()
            item.is_passed = not item.is_passed
            self.refresh_current_view()

    def toggle_hold(self):
        item = self.current_item()
        if not item:
            return
        if self.held_settings is None:
            self.held_settings = {
                "cyan": item.cyan,
                "magenta": item.magenta,
                "yellow": item.yellow,
                "density": item.density,
                "contrast": item.contrast,
                "saturation": item.saturation,
                "sharpness": item.sharpness,
                "tone_profile": item.tone_profile,
                "auto_print": item.auto_print,
                "rotation": item.rotation,
                "mirror": item.mirror,
                "auto_crop": item.auto_crop
            }
            self.btn_hold.setStyleSheet("background-color: #00E5FF; color: black; font-weight: bold;")
            changed = self.apply_held_settings(range(self.current_idx + 1, len(self.items)))
            self.statusBar().showMessage(
                f"HOLD on · settings of frame #{item.index + 1:02d} applied to {changed} following frame(s)"
                + (" (undo restores them)" if changed else ""), 5000)
        else:
            self.held_settings = None
            self.btn_hold.setStyleSheet("background-color: #E65100; color: white; font-weight: bold;")
        self.update_info_bar()

    def apply_held_settings(self, indices) -> int:
        """Copy the held settings to the given frames as one undo step. Returns the number of frames changed."""
        if not self.held_settings:
            return 0
        frames = [self.items[idx] for idx in indices]
        snapshots = [(f, self.snapshot(f)) for f in frames]
        for f in frames:
            f.cyan = self.held_settings["cyan"]
            f.magenta = self.held_settings["magenta"]
            f.yellow = self.held_settings["yellow"]
            f.density = self.held_settings["density"]
            f.contrast = self.held_settings["contrast"]
            f.saturation = self.held_settings["saturation"]
            f.sharpness = self.held_settings["sharpness"]
            f.tone_profile = self.held_settings["tone_profile"]
            f.auto_print = self.held_settings["auto_print"]
            self.set_orientation(f, self.held_settings["rotation"], self.held_settings["mirror"])
            f.auto_crop = self.held_settings["auto_crop"]
        changed = [(f, saved) for f, saved in snapshots if self.snapshot(f) != saved]
        self.last_edit = None
        self.push_undo_group(changed)
        self.refresh_current_view()
        return len(changed)

    def copy_settings(self):
        item = self.current_item()
        if item:
            self.copied_settings = {
                "cyan": item.cyan,
                "magenta": item.magenta,
                "yellow": item.yellow,
                "density": item.density,
                "contrast": item.contrast,
                "saturation": item.saturation,
                "sharpness": item.sharpness,
                "tone_profile": item.tone_profile,
                "auto_print": item.auto_print,
                "rotation": item.rotation,
                "mirror": item.mirror,
                "auto_crop": item.auto_crop
            }
            QMessageBox.information(self, "Copied", f"Settings for frame #{item.index + 1:02d} copied.")

    def paste_settings(self):
        item = self.current_item()
        if item and self.copied_settings:
            self.begin_edit()
            item.cyan = self.copied_settings["cyan"]
            item.magenta = self.copied_settings["magenta"]
            item.yellow = self.copied_settings["yellow"]
            item.density = self.copied_settings["density"]
            item.contrast = self.copied_settings["contrast"]
            item.saturation = self.copied_settings["saturation"]
            item.sharpness = self.copied_settings["sharpness"]
            item.tone_profile = self.copied_settings["tone_profile"]
            item.auto_print = self.copied_settings["auto_print"]
            self.set_orientation(item, self.copied_settings["rotation"], self.copied_settings["mirror"])
            item.auto_crop = self.copied_settings["auto_crop"]
            self.refresh_current_view()

    # ==========================================================================
    # FRAME AND BATCH NAVIGATION (6 FRAMES)
    # ==========================================================================
    def next_image(self):
        """Go forward one frame."""
        if self.current_idx < len(self.items) - 1:
            self.current_idx += 1
            self.current_page = self.current_idx // self.PAGE_SIZE
            self.refresh_current_view()

    def prev_image(self):
        """Go back one frame."""
        if self.current_idx > 0:
            self.current_idx -= 1
            self.current_page = self.current_idx // self.PAGE_SIZE
            self.refresh_current_view()

    def next_batch_six(self):
        """Jump forward 6 frames (Next 6 Frames)."""
        max_page = (len(self.items) - 1) // self.PAGE_SIZE
        if self.current_page < max_page:
            self.current_page += 1
            self.current_idx = self.current_page * self.PAGE_SIZE
            self.refresh_current_view()
        else:
            QMessageBox.information(self, "End of roll", "You are already on the last batch of 6 frames.")

    def prev_batch_six(self):
        """Jump back 6 frames (Previous 6 Frames)."""
        if self.current_page > 0:
            self.current_page -= 1
            self.current_idx = self.current_page * self.PAGE_SIZE
            self.refresh_current_view()
        else:
            QMessageBox.information(self, "Start of roll", "You are already on the first batch of 6 frames.")

    def export_batch(self):
        if not any(not item.is_passed for item in self.items):
            QMessageBox.warning(self, "Nothing to export", "No frames to export.")
            return

        options = ExportDialog(self.items, self, self.session_info,
                               self.items[self.current_idx].index if 0 <= self.current_idx < len(self.items) else None)
        if not options.exec():
            return
        self.session_info = options.info()
        self.persist_project()

        selected = options.selected_indices()
        valid = [item for item in self.items if item.index in selected and not item.is_passed]
        metadata = options.metadata()
        file_format = options.file_format.currentData()
        extension = "tif" if file_format == "tiff" else "jpg"
        try:
            names = options.output_names(valid, extension)
        except ValueError as error:
            QMessageBox.warning(self, "Export failed", str(error))
            return
        try:
            dest = create_export_folder(Path(options.destination.text().strip()).expanduser(), metadata)
        except OSError as error:
            QMessageBox.warning(self, "Export failed", str(error))
            return

        dlg = QProgressDialog("Exporting at full resolution...", "Cancel", 0, len(valid), self)
        dlg.setWindowTitle("Export")
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(0)

        exported = []
        failed = []
        export_settings = {
            "format": "TIFF 16-bit" if file_format == "tiff" else "JPEG 8-bit",
            "jpeg_quality": options.quality.value() if file_format == "jpeg" else None,
            "max_edge": options.max_edge.value(),
        }
        sequence_start, _digits = options.sequence_parameters()
        started = time.monotonic()
        embed = options.embed.isChecked()
        quality = options.quality.value()

        def fetch(item):
            return self.load_scan(item.path, full_resolution=True)

        def write(path, rendered, embedded):
            return save_image(path, rendered, embedded, quality=quality,
                              max_edge=export_settings["max_edge"], file_format=file_format)

        def collect(job):
            future, filename, photo = job
            try:
                width, height = future.result()
            except (OSError, ValueError) as error:
                failed.append(f"{filename} — {error}")
            else:
                exported.append({**photo, "width": width, "height": height})

        # pipeline: load the next frame ‖ render the current one ‖ write the previous one (identical output, faster)
        loader = ThreadPoolExecutor(max_workers=1, thread_name_prefix="smneg-export-load")
        writer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="smneg-export-save")
        next_load = loader.submit(fetch, valid[0]) if valid else None
        previous_job = None
        try:
            for i, item in enumerate(valid):
                remaining = ""
                if i:
                    remaining = f"\nTime remaining: ~{format_duration((time.monotonic() - started) / i * (len(valid) - i))}"
                dlg.setLabelText(f"Frame {i + 1} / {len(valid)} — {names[i]}{remaining}")
                dlg.setValue(i)
                if dlg.wasCanceled():
                    break

                base_full = next_load.result()
                next_load = loader.submit(fetch, valid[i + 1]) if i + 1 < len(valid) else None
                if base_full is None:
                    # never write a preview-resolution image in place of the full-resolution one
                    failed.append(f"{names[i]} — {Path(item.path).name} could not be decoded at full "
                                  f"resolution ({self.load_error(item.path)}); not exported")
                    continue

                rendered = self.render_frame(item, base_full, output_16bit=file_format == "tiff")
                base_full = None
                source = Path(item.path)
                sequence = sequence_start + i
                filename = names[i]
                try:
                    source_modified_at = datetime.fromtimestamp(source.stat().st_mtime).astimezone().isoformat(timespec="seconds")
                except OSError:
                    source_modified_at = None
                photo = {
                    "file": filename,
                    "sequence": sequence,
                    "source": source.name,
                    "processed_date": item.processed_date,
                    "source_modified_at": source_modified_at,
                    "resolution": "full",
                }
                embedded = {**asdict(metadata), **export_settings, **photo} if embed else None
                if previous_job is not None:
                    collect(previous_job)
                previous_job = (writer.submit(write, dest / filename, rendered, embedded), filename, photo)
                rendered = None
            if previous_job is not None:
                collect(previous_job)
        finally:
            loader.shutdown(wait=False, cancel_futures=True)
            writer.shutdown(wait=True)

        cancelled = dlg.wasCanceled()
        dlg.close()
        if options.sidecar.isChecked():
            try:
                (dest / "metadata.json").write_text(
                    json.dumps({**asdict(metadata), **export_settings, "photos": exported}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except OSError as error:
                failed.append(f"metadata.json — {error}")

        summary = f"{len(exported)} scans exported as {export_settings['format']}.\n{dest}"
        if cancelled:
            summary += "\nExport interrupted."
        if file_format == "tiff" and options.embed.isChecked() and not TIFF_METADATA_AVAILABLE:
            summary += "\nMetadata not embedded in the TIFF: install the module with  pip install tifffile"
        summary += f"\nDuration: {format_duration(time.monotonic() - started)}"
        if failed:
            summary += "\nNot exported:\n" + "\n".join(failed)
        box = QMessageBox(self)
        box.setWindowTitle("Export finished")
        box.setIcon(QMessageBox.Icon.Warning if failed else QMessageBox.Icon.Information)
        box.setText(summary)
        finder = box.addButton("Show in Finder" if sys.platform == "darwin" else "Show in folder", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Close)
        box.setDefaultButton(finder)
        box.exec()
        if box.clickedButton() is finder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(dest)))

    # ==========================================================================
    # KEYBOARD CONTROLLER
    # ==========================================================================
    def keyPressEvent(self, event: QKeyEvent):
        k = event.key()
        mod = event.modifiers()
        is_cmd = bool(mod & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier))
        is_alt = bool(mod & Qt.KeyboardModifier.AltModifier)
        is_shift = bool(mod & Qt.KeyboardModifier.ShiftModifier)

        # leave the Enlarged view and go back to the Grid
        if k == Qt.Key.Key_Escape and self.large_preview.canvas.is_picking():
            self.cancel_pick()
            return
        if k == Qt.Key.Key_Escape:
            if self.large_preview.canvas.is_zoomed():
                self.large_preview.canvas.reset_fit()
            elif self.stack.currentIndex() == 1:
                self.switch_to_grid_view()
            return

        if k in (Qt.Key.Key_F1, Qt.Key.Key_Question):
            self.show_shortcuts()
            return

        # Undo / Redo / Export
        if is_cmd and k == Qt.Key.Key_Z:
            self.redo() if is_shift else self.undo()
            return
        if is_cmd and k == Qt.Key.Key_E:
            self.export_batch()
            return

        # -------------------------------------------------------------
        # 6-frame navigation (CMD + Shift + ← / → / Backspace)
        # -------------------------------------------------------------
        if is_cmd and is_shift:
            if k in (Qt.Key.Key_Left, Qt.Key.Key_Backspace):
                self.prev_batch_six()
                return
            elif k == Qt.Key.Key_Right:
                self.next_batch_six()
                return

        # Copy / Paste Settings
        if is_cmd and k == Qt.Key.Key_C:
            self.copy_settings()
            return
        elif is_cmd and k == Qt.Key.Key_V:
            self.paste_settings()
            return

        # CMY / RGB (Q, W, E / A, S, D)
        if k == Qt.Key.Key_Q and not is_cmd:
            self.adjust_color("C", 1)
        elif k == Qt.Key.Key_A and not is_cmd:
            self.adjust_color("C", -1)
        elif k == Qt.Key.Key_W and not is_cmd:
            self.adjust_color("M", 1)
        elif k == Qt.Key.Key_S and not is_cmd:
            self.adjust_color("M", -1)
        elif k == Qt.Key.Key_E and not is_cmd:
            self.adjust_color("Y", 1)
        elif k == Qt.Key.Key_D and not is_cmd:
            self.adjust_color("Y", -1)

        # Up / Down arrows
        elif k == Qt.Key.Key_Up:
            if is_cmd:
                self.adjust_saturation(0.1)
            elif is_alt:
                self.adjust_contrast(0.05)
            else:
                self.adjust_density(1)
        elif k == Qt.Key.Key_Down:
            if is_cmd:
                self.adjust_saturation(-0.1)
            elif is_alt:
                self.adjust_contrast(-0.05)
            else:
                self.adjust_density(-1)

        # Left / Right arrows
        elif k == Qt.Key.Key_Left:
            if is_cmd:
                self.prev_image()          # one frame back
            else:
                self.rotate_ccw()          # rotate
        elif k == Qt.Key.Key_Right:
            if is_cmd:
                self.next_image()          # one frame forward
            else:
                self.rotate_cw()           # rotate

        # Tools
        elif k == Qt.Key.Key_M and not is_cmd:
            self.toggle_mirror()
        elif k in (Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Meta, Qt.Key.Key_Alt):
            return  # a lone modifier key press does nothing
        elif k == Qt.Key.Key_X and not is_cmd:
            self.toggle_clipping()
        elif k == Qt.Key.Key_C and not is_cmd:
            self.toggle_auto_crop()
        elif k == Qt.Key.Key_P and not is_cmd:
            self.toggle_pass()
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.next_image()
        elif k == Qt.Key.Key_Space:
            self.toggle_view()
        elif k == Qt.Key.Key_Z and not is_cmd:
            self.open_zoom()
        elif k == Qt.Key.Key_O and not is_cmd:
            self.open_original()
        elif k == Qt.Key.Key_K and not is_cmd:
            self.open_manual_crop()
        elif k == Qt.Key.Key_H and not is_cmd:
            self.toggle_hold()
        elif k == Qt.Key.Key_R and not is_cmd:
            self.reset_frame()
        elif k == Qt.Key.Key_N and not is_cmd:
            self.clear_grey_picks() if is_shift else self.start_pick("grey")
        elif k == Qt.Key.Key_B and not is_cmd:
            self.clear_base_pick() if is_shift else self.start_pick("base")
        elif k == Qt.Key.Key_L and not is_cmd:
            self.toggle_auto_print()
        elif k == Qt.Key.Key_T and not is_cmd:
            self.cycle_tone_profile()

        else:
            super().keyPressEvent(event)
