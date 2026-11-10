from types import SimpleNamespace

import numpy as np
import pytest

from smneg.crop import rotate_crop
from smneg.models import FrameItem
from smneg.window import SMnegWindow

# stand-in window for the Classic engine (render_frame only needs these attributes)
CLASSIC = SimpleNamespace(engine='classic', sharpen=SMnegWindow.sharpen)


@pytest.mark.parametrize('clockwise', [True, False])
@pytest.mark.parametrize('bits', [8, 16])
def test_rotating_cropped_image_keeps_same_content(clockwise, bits):
    base = np.random.default_rng(5).random((80, 120, 3), dtype=np.float32)
    item = FrameItem(0, 'unused', base, manual_crop=(0.125, 0.25, 0.625, 0.875), straighten=0.0)
    render = SMnegWindow.render_frame if bits == 8 else SMnegWindow.render_frame_16bit
    before = render(CLASSIC, item, base)
    edits = []
    app = SimpleNamespace(current_item=lambda: item, begin_edit=lambda: edits.append(item.manual_crop),
                          refresh_current_view=lambda: None)
    method = SMnegWindow.rotate_cw if clockwise else SMnegWindow.rotate_ccw
    method(app)
    after = render(CLASSIC, item, base)
    expected = np.rot90(before, -1 if clockwise else 1)
    np.testing.assert_array_equal(after, expected)
    assert edits == [(0.125, 0.25, 0.625, 0.875)]


def test_four_turns_restore_crop_and_none_stays_none():
    bounds = (0.125, 0.25, 0.625, 0.75)
    result = bounds
    for _ in range(4):
        result = rotate_crop(result)
    assert result == bounds
    assert rotate_crop(None) is None
    assert rotate_crop(rotate_crop(bounds), clockwise=False) == bounds


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('bits', [8, 16])
def test_mirror_keeps_selected_content_in_each_orientation(rotation, bits):
    base = np.random.default_rng(8).random((80, 120, 3), dtype=np.float32)
    item = FrameItem(0, 'unused', base, rotation=rotation,
                     manual_crop=(0.125, 0.25, 0.625, 0.875))
    render = SMnegWindow.render_frame if bits == 8 else SMnegWindow.render_frame_16bit
    before = render(CLASSIC, item, base)
    app = SimpleNamespace(current_item=lambda: item, begin_edit=lambda: None,
                          refresh_current_view=lambda: None)
    SMnegWindow.toggle_mirror(app)
    after = render(CLASSIC, item, base)
    expected = np.flipud(before) if rotation % 180 else np.fliplr(before)
    np.testing.assert_array_equal(after, expected)


def test_paste_orientation_preserves_target_crop():
    from smneg.crop import set_frame_orientation
    base = np.random.default_rng(9).random((80, 120, 3), dtype=np.float32)
    item = FrameItem(0, 'unused', base, manual_crop=(0.125, 0.25, 0.625, 0.875))
    before = SMnegWindow.render_frame(CLASSIC, item, base)
    settings = SMnegWindow.snapshot(item)
    settings.update(rotation=90, mirror=True)
    app = SimpleNamespace(current_item=lambda: item, copied_settings=settings,
                          begin_edit=lambda: None, refresh_current_view=lambda: None)
    SMnegWindow.paste_settings(app)
    np.testing.assert_array_equal(SMnegWindow.render_frame(CLASSIC, item, base),
                                  np.rot90(np.fliplr(before), -1))
    set_frame_orientation(item, 0, False)
    np.testing.assert_array_equal(SMnegWindow.render_frame(CLASSIC, item, base), before)
