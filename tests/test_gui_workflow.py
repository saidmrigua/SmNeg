# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
"""Real Qt workflow tests with private settings and synthetic scans."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from smneg import session, window
from smneg.export import save_image
from smneg.models import FrameItem


@pytest.fixture
def gui(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])

    def private_settings():
        return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)

    monkeypatch.setattr(window, "app_settings", private_settings)
    monkeypatch.setattr(session, "app_settings", private_settings)
    monkeypatch.setattr(window.SMnegWindow, "restore_startup", lambda self: None)
    widget = window.SMnegWindow()
    widget.show()
    app.processEvents()
    yield widget
    widget.session_timer.stop()
    widget.hot_timer.stop()
    widget.close()
    app.processEvents()


@pytest.mark.parametrize("clockwise", [True, False])
def test_crop_rotation_undo_redo_session(gui, tmp_path, clockwise):
    base = np.random.default_rng(3).random((80, 120, 3), dtype=np.float32)
    crop = (0.125, 0.25, 0.625, 0.875)
    item = FrameItem(0, str(tmp_path / "negative.tif"), base, manual_crop=crop)
    gui.items = [item]
    gui.session_folder = tmp_path
    gui.refresh_current_view()
    before = gui.render_item(item)
    (gui.rotate_cw if clockwise else gui.rotate_ccw)()
    expected = np.rot90(before, -1 if clockwise else 1)
    np.testing.assert_array_equal(gui.render_item(item), expected)
    gui.undo()
    assert item.rotation == 0 and item.manual_crop == crop
    gui.redo()
    np.testing.assert_array_equal(gui.render_item(item), expected)
    assert gui.persist_project()
    saved = session.read_project(tmp_path)["frames"][0]
    assert saved["rotation"] == item.rotation
    assert saved["manual_crop"] == list(item.manual_crop)
    gui.toggle_mirror()
    gui.undo()
    np.testing.assert_array_equal(gui.render_item(item), expected)


def test_crop_tiff_export(gui, tmp_path):
    tifffile = pytest.importorskip("tifffile")
    base = np.random.default_rng(4).random((80, 120, 3), dtype=np.float32)
    item = FrameItem(0, "negative.tif", base, manual_crop=(0.125, 0.25, 0.625, 0.875))
    gui.items = [item]
    gui.rotate_ccw()
    pixels = gui.render_frame(item, base, output_16bit=True)
    output = tmp_path / "positive.tif"
    save_image(output, pixels, {"photographer": "Said Mrigua", "film": "test"}, file_format="tiff")
    np.testing.assert_array_equal(tifffile.imread(output), pixels)
    with tifffile.TiffFile(output) as image:
        assert image.pages[0].dtype == np.uint16
        assert b"Said Mrigua" in image.pages[0].tags["XMP"].value


def test_auto_crop_key_keeps_a_manual_crop(gui, tmp_path):
    base = np.random.default_rng(4).random((80, 120, 3), dtype=np.float32)
    crop = (0.125, 0.25, 0.625, 0.875)
    item = FrameItem(0, str(tmp_path / "negative.tif"), base, manual_crop=crop)
    gui.items = [item]
    gui.refresh_current_view()
    before = gui.render_item(item)
    gui.toggle_auto_crop()
    assert item.manual_crop == crop and not item.auto_crop
    np.testing.assert_array_equal(gui.render_item(item), before)
    assert "manual crop" in gui.statusBar().currentMessage()
    item.manual_crop = None
    gui.toggle_auto_crop()
    assert item.auto_crop


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_mirror_flips_left_to_right_as_seen(gui, tmp_path, rotation):
    base = np.random.default_rng(6).random((80, 120, 3), dtype=np.float32)
    item = FrameItem(0, str(tmp_path / "negative.tif"), base, manual_crop=(0.125, 0.25, 0.625, 0.875))
    gui.items = [item]
    gui.refresh_current_view()
    gui.set_orientation(item, rotation, False)
    before = gui.render_item(item)
    gui.toggle_mirror()
    np.testing.assert_array_equal(gui.render_item(item), np.fliplr(before))
    gui.toggle_mirror()
    np.testing.assert_array_equal(gui.render_item(item), before)
    gui.undo()
    gui.undo()
    assert (item.rotation, item.mirror) == (rotation, False)


def test_windows_are_srgb():
    from PySide6.QtGui import QColorSpace, QSurfaceFormat
    from smneg.app import use_srgb_windows
    saved = QSurfaceFormat.defaultFormat()
    try:
        use_srgb_windows()
        assert QSurfaceFormat.defaultFormat().colorSpace() == QColorSpace(QColorSpace.NamedColorSpace.SRgb)
    finally:
        QSurfaceFormat.setDefaultFormat(saved)


def test_jpeg_export_says_srgb_in_exif_and_icc(tmp_path):
    from PIL import Image
    from smneg.export import SRGB_ICC
    path = tmp_path / "out.jpg"
    save_image(path, np.full((20, 30, 3), 128, np.uint8))
    with Image.open(path) as image:
        assert image.getexif().get_ifd(0x8769).get(0xA001) == 1
        assert image.info["icc_profile"] == SRGB_ICC
