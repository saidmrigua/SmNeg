"""Scientific engine through the real window: pickers, Auto print, profiles, HOLD, import (offscreen Qt)."""
import os
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

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
    private = lambda: QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    monkeypatch.setattr(window, 'app_settings', private)
    monkeypatch.setattr(session, 'app_settings', private)
    monkeypatch.setattr(window.SMnegWindow, 'restore_startup', lambda self: None)
    widget = window.SMnegWindow()
    widget.show()
    app.processEvents()
    yield app, widget
    widget.session_timer.stop()
    widget.hot_timer.stop()
    widget.close()
    app.processEvents()


def _roll(tmp_path, count=4):
    base = np.random.default_rng(5).random((30, 40, 3), dtype=np.float32)
    return [FrameItem(i, str(tmp_path / f'f{i}.nef'), base) for i in range(count)]


def test_hold_keeps_edits_on_the_current_frame(gui, tmp_path):
    _, widget = gui
    widget.items = _roll(tmp_path)
    widget.adjust_color('C', 3)
    widget.toggle_hold()
    widget.adjust_color('C', 1)
    widget.adjust_density(5)
    assert widget.items[0].cyan == 4
    assert widget.items[0].density == 5


def test_hold_copies_settings_forward_as_one_undo_step(gui, tmp_path):
    _, widget = gui
    widget.items = _roll(tmp_path)
    widget.items[3].magenta = -2                       # an individual correction on a later frame
    widget.current_idx = 1
    widget.adjust_color('Y', 2)
    widget.rotate_cw()
    widget.toggle_hold()
    assert [f.yellow for f in widget.items] == [0, 2, 2, 2]
    assert [f.rotation for f in widget.items] == [0, 90, 90, 90]
    assert widget.items[3].magenta == 0
    widget.undo()                                      # restores frames 2 and 3 together
    assert [f.yellow for f in widget.items] == [0, 2, 0, 0]
    assert widget.items[3].magenta == -2 and widget.items[2].rotation == 0
    widget.redo()
    assert [f.yellow for f in widget.items] == [0, 2, 2, 2]


def test_hold_off_does_not_touch_other_frames(gui, tmp_path):
    _, widget = gui
    widget.items = _roll(tmp_path)
    widget.toggle_hold()
    widget.toggle_hold()
    assert widget.held_settings is None
    widget.adjust_color('M', 1)
    assert [f.magenta for f in widget.items] == [1, 0, 0, 0]


def _synthetic_negatives(folder, count=3):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent / 'audit'))
    from audit_color import LIGHTS, STOCKS, expose, scene
    tifffile = pytest.importorskip('tifffile')
    paths = []
    for i in range(count):
        refl, _, rebate = scene(('balanced', 'warm', 'cool')[i], np.random.default_rng(i), 240, 360, small_wedge=True)
        raw = expose(refl, rebate, STOCKS['Portra-like'], LIGHTS['D65'])
        path = folder / f'neg{i}.tif'
        tifffile.imwrite(path, np.rint(raw * 65535).astype(np.uint16), photometric='rgb')
        paths.append(path)
    return paths


def test_scientific_engine_import_render_and_tagged_export(gui, tmp_path):
    from PIL import Image
    tifffile = pytest.importorskip('tifffile')
    _, widget = gui
    assert widget.engine == 'scientific'
    for path in _synthetic_negatives(tmp_path):
        assert widget.import_frame(str(path))
    widget.refresh_current_view()
    item = widget.items[0]
    assert item.stats.source == 'rebate'
    assert 'Base: rebate' in widget.lbl_info.text() and 'C+0 M+0 Y+0 D+0' in widget.lbl_info.text()
    preview = widget.render_item(item)
    assert preview.dtype == np.uint8 and preview.shape == (240, 360, 3)
    pixels = widget.render_frame(item, item.base_positive, output_16bit=True)
    assert pixels.dtype == np.uint16
    tiff, jpeg = tmp_path / 'out.tif', tmp_path / 'out.jpg'
    save_image(tiff, pixels, None, file_format='tiff')
    save_image(jpeg, preview, None)
    with tifffile.TiffFile(tiff) as image:
        assert 34675 in image.pages[0].tags                 # ICC profile tag
    with Image.open(jpeg) as image:
        assert image.info.get('icc_profile')


def test_sessions_remember_the_engine(gui, tmp_path):
    _, widget = gui
    widget.apply_session_engine({'frames': [{'path': 'x.nef'}]})   # saved before the engine existed
    assert widget.engine == 'classic' and widget.engine_box.currentData() == 'classic'
    widget.apply_session_engine({'engine': 'scientific', 'frames': [{'path': 'x.nef'}]})
    assert widget.engine == 'scientific'
    session.write_project(tmp_path, [], 0, 0, {}, '', {}, 'scientific')
    assert session.read_project(tmp_path)['engine'] == 'scientific'
    with pytest.raises(ValueError):
        session.validate_session({'engine': 'magic'})


@pytest.mark.parametrize('rotation, mirror, auto_crop, crop, straighten', [
    (0, False, False, None, 0.0),
    (90, False, False, None, 0.0),
    (180, True, False, None, 0.0),
    (270, False, True, None, 0.0),
    (90, True, False, (0.1, 0.2, 0.8, 0.9), 0.0),
    (0, False, False, (0.05, 0.1, 0.9, 0.95), 3.0),
])
def test_click_maps_to_the_right_scan_pixel(gui, rotation, mirror, auto_crop, crop, straighten):
    _, widget = gui
    values = np.full((120, 180, 3), 0.05, np.float32)
    values[:6] = values[-6:] = (0.6, 0.35, 0.15)              # rebate
    marker = (70, 50)                                          # x, y of a clear marker in the scan
    values[marker[1] - 3:marker[1] + 4, marker[0] - 3:marker[0] + 4] = (0.004, 0.002, 0.001)
    item = FrameItem(0, 'synthetic.tif', values, rotation=rotation, mirror=mirror, auto_crop=auto_crop,
                     manual_crop=crop, straighten=straighten)
    widget.items = [item]
    shown = widget.render_item(item).astype(int).sum(-1)
    ys, xs = np.nonzero(shown >= shown.max() - 30)            # densest spot -> brightest in the positive
    u, v = (xs.mean() + 0.5) / shown.shape[1], (ys.mean() + 0.5) / shown.shape[0]
    x, y = widget.source_point(item, u, v)
    assert abs(x - marker[0]) <= 2 and abs(y - marker[1]) <= 2


def test_grey_pick_neutralizes_the_clicked_patch(gui, tmp_path):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent / 'audit'))
    from audit_color import LIGHTS, STOCKS, expose, scene, srgb_to_lab
    _, widget = gui
    refl, boxes, rebate = scene('cool', np.random.default_rng(2), 300, 450, small_wedge=True)
    raw = expose(refl, rebate, STOCKS['Portra-like'], LIGHTS['LED'])
    item = FrameItem(0, 'cool.tif', raw, cyan=7, yellow=-6)        # a visible cast to remove
    widget.items = [item]
    widget.switch_to_large_view(0)
    a, b, c, d = boxes[10]
    before = srgb_to_lab(widget.render_item(item)[a:b, c:d].reshape(-1, 3).mean(0) / 255)
    widget.pick_kind = 'grey'
    widget.on_point_picked((c + d) / 2 / 450, (a + b) / 2 / 300)
    after = srgb_to_lab(widget.render_item(item)[a:b, c:d].reshape(-1, 3).mean(0) / 255)
    assert np.hypot(after[1], after[2]) < 1.0 <= np.hypot(before[1], before[2])
    widget.undo()
    assert (item.cyan, item.yellow) == (7, -6)


def test_base_pick_is_used_saved_and_undoable(gui, tmp_path):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent / 'audit'))
    from audit_color import LIGHTS, STOCKS, expose, scene
    _, widget = gui
    refl, _, rebate = scene('balanced', np.random.default_rng(5), 300, 450, small_wedge=True)
    raw = expose(refl, rebate, STOCKS['Portra-like'], LIGHTS['D65'])
    other = raw.copy()
    other[rebate] = raw[~rebate].max(0) * 0.98                 # second frame: rebate hidden
    first, second = FrameItem(0, 'a.tif', raw), FrameItem(1, 'b.tif', other)
    widget.items = [first, second]
    widget.session_folder = tmp_path
    widget.switch_to_large_view(0)
    widget.pick_kind = 'base'
    widget.on_point_picked(0.5, 4 / 300)                       # top rebate strip
    true_base = np.median(raw[rebate], axis=0)
    assert np.allclose(first.base_pick, true_base, rtol=0.01)
    assert 'Base: picked' in widget.lbl_info.text()
    assert np.allclose(widget.roll().base, true_base, rtol=0.01)  # the roll uses the picked base
    assert widget.persist_project()
    assert np.allclose(session.read_project(tmp_path)['frames'][0]['base_pick'], true_base, rtol=0.01)
    widget.undo()
    assert first.base_pick is None
    with pytest.raises(ValueError):
        session.validate_session({'frames': [{'path': 'x', 'base_pick': [0.5, -1, 0.2]}]})


def test_camera_profile_is_used_and_saved_with_the_session(gui, tmp_path):
    import json
    _, widget = gui
    profile = tmp_path / 'z8.json'
    profile.write_text(json.dumps({'camera_rgb_to_xyz_d50': [[2.15, 0.33, 0.09], [0.87, 1.37, -0.33],
                                                             [0.03, -0.24, 1.87]]}))
    paths = _synthetic_negatives(tmp_path, 1)
    assert widget.import_frame(str(paths[0]))
    widget.session_folder = tmp_path
    before = widget.render_item(widget.items[0]).copy()
    assert widget.set_camera_profile(str(profile))
    widget.refresh_current_view()
    assert 'Profile: z8' in widget.lbl_info.text() and widget.btn_profile.text() == 'CAMERA: z8'
    assert not np.array_equal(before, widget.render_item(widget.items[0]))
    assert session.read_project(tmp_path)['camera_profile'] == str(profile)
    widget.set_camera_profile('')
    np.testing.assert_array_equal(before, widget.render_item(widget.items[0]))
    widget.apply_session_engine({'engine': 'scientific', 'camera_profile': str(tmp_path / 'missing.json')})
    assert widget.camera_profile is None                                  # missing file: warned, not fatal


def test_film_calibration_from_a_colorchecker(gui, tmp_path, monkeypatch):
    from film_chart import chart_negative
    from smneg import film_profile as fp
    _, widget = gui
    raw, centres, _, _ = chart_negative('Portra-like', 'LED')
    item = FrameItem(0, str(tmp_path / 'chart.nef'), raw.astype(np.float32))
    widget.items = [item]
    widget.session_folder = tmp_path
    monkeypatch.setattr(window.SMnegWindow, 'film_profile_dir', staticmethod(lambda: tmp_path / 'profiles'))
    monkeypatch.setattr(window.QInputDialog, 'getText', staticmethod(lambda *a, **k: ('Portra test', True)))
    before = widget.render_item(item).copy()
    widget.start_pick('chart')
    h, w = raw.shape[:2]
    for index in (23, 0, 18, 5):                       # corner patches, any order
        x, y = centres[index]
        widget.on_point_picked((x + 0.5) / w, (y + 0.5) / h)
    assert widget.film_profile is not None and widget.film_profile.name == 'Portra test'
    saved = tmp_path / 'profiles' / 'Portra test.json'
    assert saved.is_file() and fp.load_film_profile(saved).delta_e_after < fp.load_film_profile(saved).delta_e_before
    widget.refresh_current_view()
    assert 'Film: Portra test' in widget.lbl_info.text() and widget.btn_film.text() == 'FILM: Portra test'
    assert not np.array_equal(before, widget.render_item(item))
    assert session.read_project(tmp_path)['film_profile'] == str(saved)
    widget.set_film_profile('')
    np.testing.assert_array_equal(before, widget.render_item(item))


def test_auto_print_switch(gui, tmp_path):
    _, widget = gui
    paths = _synthetic_negatives(tmp_path, 2)
    for path in paths:
        assert widget.import_frame(str(path))
    widget.refresh_current_view()
    item = widget.items[0]
    assert item.auto_print and 'Auto print' in widget.lbl_info.text()
    printed = widget.render_item(item).copy()
    widget.toggle_auto_print()
    assert not item.auto_print and 'Flat master' in widget.lbl_info.text()
    assert widget.btn_auto_print.text() == 'FLAT MASTER [L]'
    assert not np.array_equal(printed, widget.render_item(item))
    widget.undo()
    assert item.auto_print
    np.testing.assert_array_equal(printed, widget.render_item(item))


def test_folder_import_reads_in_parallel_and_reports_bad_files(gui, tmp_path, monkeypatch):
    _, widget = gui
    folder = tmp_path / 'roll'
    folder.mkdir()
    for path in _synthetic_negatives(folder, 3):
        assert path.exists()
    (folder / 'broken.tif').write_bytes(b'not a tiff')
    warnings = []
    monkeypatch.setattr(window.QFileDialog, 'getExistingDirectory', staticmethod(lambda *a, **k: str(folder)))
    monkeypatch.setattr(window.QMessageBox, 'warning', staticmethod(lambda *a, **k: warnings.append(a[2])))
    widget.select_roll_folder()
    assert [Path(item.path).name for item in widget.items] == ['neg0.tif', 'neg1.tif', 'neg2.tif']
    assert all(item.stats is not None for item in widget.items)
    assert warnings and 'broken.tif' in warnings[0]


def test_film_base_reference_is_used_saved_and_cleared(gui, tmp_path):
    import tifffile
    _, widget = gui
    paths = _synthetic_negatives(tmp_path, 2)
    for path in paths:
        assert widget.import_frame(str(path))
    leader_value = np.array([0.80, 0.36, 0.18], np.float32)
    leader = tmp_path / 'leader.tif'
    tifffile.imwrite(leader, np.rint(np.tile(leader_value, (80, 120, 1)) * 65535).astype(np.uint16), photometric='rgb')
    widget.session_folder = tmp_path
    assert widget.set_base_reference([str(leader)])
    np.testing.assert_allclose(widget.roll().base, leader_value, rtol=0.01)
    saved = session.read_project(tmp_path)['film_base_reference']
    assert saved['files'] == [str(leader)] and np.allclose(saved['base'], leader_value, rtol=0.01)
    widget.set_base_reference(None)
    assert widget.base_reference is None and 'film_base_reference' not in session.read_project(tmp_path)
    widget.apply_session_engine({'engine': 'scientific', 'film_base_reference': saved})     # reopening the session
    np.testing.assert_allclose(widget.base_reference, leader_value, rtol=0.01)
    with pytest.raises(ValueError):
        session.validate_session({'film_base_reference': {'files': [], 'base': [0.5, 'x', 0.2]}})


def test_meter_choice_changes_auto_print_and_is_saved(gui, tmp_path):
    _, widget = gui
    for path in _synthetic_negatives(tmp_path, 3):
        assert widget.import_frame(str(path))
    widget.session_folder = tmp_path
    assert widget.meter == 'balanced'
    balanced = widget.render_item(widget.items[1]).copy()
    widget.set_meter('roll')
    assert not np.array_equal(balanced, widget.render_item(widget.items[1]))
    assert session.read_project(tmp_path)['meter'] == 'roll' and widget.meter_box.currentData() == 'roll'
    widget.apply_session_engine({'engine': 'scientific', 'meter': 'frame'})
    assert widget.meter == 'frame'
    with pytest.raises(ValueError):
        session.validate_session({'meter': 'magic'})


def test_roll_balance_is_saved_and_helps_a_single_frame(gui, tmp_path, monkeypatch):
    import sys
    sys.path.insert(0, str(Path(__file__).parent / 'audit'))
    from audit_color import LIGHTS, STOCKS, expose, patch_lab, scene
    from smneg import film_profile as fp
    from smneg import scientific as sc
    _, widget = gui
    stock, light = STOCKS['Portra-like'], LIGHTS['D65']

    def frame(content, ev, seed):
        refl, boxes, rebate = scene(content, np.random.default_rng(seed), 240, 360, small_wedge=True)
        return expose(refl, rebate, stock, light, ev), boxes

    messages = []
    monkeypatch.setattr(window.QMessageBox, 'information', staticmethod(lambda *a, **k: messages.append(a[2])))
    monkeypatch.setattr(window.SMnegWindow, 'film_profile_dir', staticmethod(lambda: tmp_path / 'profiles'))
    monkeypatch.setattr(window.QInputDialog, 'getText', staticmethod(lambda *a, **k: ('Portra balance', True)))
    widget.items = [FrameItem(0, 'a.nef', frame('balanced', 0, 1)[0])]
    widget.save_roll_balance()
    assert messages and 'at least 6' in messages[0]                     # one frame is not a roll
    widget.items = [FrameItem(i, f'{i}.nef', frame(c, ev, 11)[0]) for i, (c, ev) in enumerate(
        (c, ev) for c in ('balanced', 'warm', 'cool', 'low-key', 'high-key') for ev in (-1, 1))]
    widget.save_roll_balance()
    saved = fp.load_film_profile(tmp_path / 'profiles' / 'Portra balance.json')
    assert np.allclose(saved.matrix, np.eye(3)) and saved.chart.startswith('roll balance')

    raw, boxes = frame('cool', 0, 22)                                   # a new frame, on its own
    stats = sc.frame_stats(raw)
    chroma = []
    for film in (None, saved):
        params = sc.frame_params(stats, sc.roll_model([stats], film), film)
        lab = patch_lab(sc.render(raw, params, output_float=True).astype(np.float64), boxes)
        chroma.append(np.hypot(lab[:, 1], lab[:, 2]).mean())
    assert chroma[1] < 2.5                                # the saved balance keeps a lone frame neutral


def test_two_grey_picks_remove_the_cast_from_highlights_to_shadows(gui, tmp_path):
    import sys
    sys.path.insert(0, str(Path(__file__).parent / 'audit'))
    from audit_color import LIGHTS, STOCKS, expose, patch_lab, scene
    _, widget = gui
    refl, boxes, rebate = scene('cool', np.random.default_rng(22), 300, 450, small_wedge=True)
    raw = expose(refl, rebate, STOCKS['Portra-like'], LIGHTS['D65'])
    item = FrameItem(0, 'cool.tif', raw, auto_print=False)
    widget.items = [item]
    widget.session_folder = tmp_path
    widget.switch_to_large_view(0)

    def chroma():
        lab = patch_lab(widget.render_frame(item, raw, output_16bit=True).astype(np.float64) / 65535, boxes)
        return np.hypot(lab[:, 1], lab[:, 2])

    def click(patch):
        a, b, c, d = boxes[patch]
        widget.pick_kind = 'grey'
        widget.on_point_picked((c + d) / 2 / 450, (a + b) / 2 / 300)

    before = chroma()
    click(4)                                             # a light grey: offset only
    one = chroma()
    assert len(item.grey_picks) == 1 and one.mean() <= before.mean() + 0.05
    click(14)                                            # a dark grey: tilt as well
    two = chroma()
    assert len(item.grey_picks) == 2 and 'Grey picks: 2' in widget.lbl_info.text()
    assert two.mean() < 1.0 and two[:8].mean() < one[:8].mean() + 0.2 and two.mean() <= one.mean() + 0.05
    assert widget.persist_project() and len(session.read_project(tmp_path)['frames'][0]['grey_picks']) == 2
    widget.undo()
    assert len(item.grey_picks) == 1
    widget.redo()
    widget.clear_grey_picks()
    assert item.grey_picks is None and (item.cyan, item.yellow) == (item.magenta, item.magenta)
    with pytest.raises(ValueError):
        session.validate_session({'frames': [{'path': 'x', 'grey_picks': [[0.2, 0.3]]}]})
