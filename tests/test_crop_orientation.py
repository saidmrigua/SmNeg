# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
"""A manual crop must keep framing the same picture content when the frame is rotated or mirrored."""
import itertools

import numpy as np
import pytest

from smneg.crop import apply_crop, flip_bounds, from_source_bounds, reorient, rotate_bounds, to_source_bounds

ORIENTATIONS = list(itertools.product((0, 90, 180, 270), (False, True)))


def display(image, rotation, mirror):
    """The geometry of OfficialFilmEngine.apply_pipeline: mirror first, then rotate clockwise."""
    if mirror:
        image = np.fliplr(image)
    return np.rot90(image, -((rotation % 360) // 90))


@pytest.fixture
def scene():
    # 40 rows x 60 columns, every pixel different, so any shift in the crop changes the result
    return np.arange(40 * 60 * 3, dtype=np.int32).reshape(40, 60, 3)


@pytest.mark.parametrize("old", ORIENTATIONS)
@pytest.mark.parametrize("new", ORIENTATIONS)
def test_crop_follows_the_content(scene, old, new):
    box_old = (0.25, 0.5, 0.75, 1.0)                    # drawn on the old displayed image
    framed = apply_crop(display(scene, *old), box_old)
    box_new, _ = reorient(box_old, 0.0, old, new)
    result = apply_crop(display(scene, *new), box_new)
    # the same part of the scene, only turned / mirrored like the rest of the picture
    source_box = to_source_bounds(box_old, *old)
    expected = display(apply_crop(scene, source_box), *new)
    assert result.shape == expected.shape
    np.testing.assert_array_equal(result, expected)
    # and it is the same content as before the change, seen through the same turn
    assert sorted(framed.flatten()) == sorted(result.flatten())


@pytest.mark.parametrize("orientation", ORIENTATIONS)
def test_source_round_trip(orientation):
    box = (0.1, 0.2, 0.6, 0.9)
    assert from_source_bounds(to_source_bounds(box, *orientation), *orientation) == pytest.approx(box)


def test_four_quarter_turns_return_the_same_box():
    box = (0.1, 0.2, 0.6, 0.9)
    for clockwise in (True, False):
        turned = box
        for _ in range(4):
            turned = rotate_bounds(turned, clockwise)
        assert turned == pytest.approx(box)
    assert flip_bounds(flip_bounds(box)) == pytest.approx(box)


def test_no_crop_stays_no_crop():
    assert reorient(None, 0.0, (0, False), (90, True)) == (None, 0.0)


def test_straighten_angle_reverses_only_when_the_mirror_changes():
    assert reorient(None, 1.5, (0, False), (90, False))[1] == 1.5
    assert reorient(None, 1.5, (0, False), (0, True))[1] == -1.5
    assert reorient(None, 1.5, (0, True), (180, True))[1] == 1.5


def undisplay(image, rotation, mirror):
    image = np.rot90(image, (rotation % 360) // 90)
    return np.fliplr(image) if mirror else image


@pytest.mark.parametrize("old", ORIENTATIONS)
@pytest.mark.parametrize("new", ORIENTATIONS)
def test_straightened_picture_stays_the_same_after_reorienting(old, new):
    from smneg.crop import straighten_image
    rows, cols = np.mgrid[0:60, 0:80]
    scene = np.stack([np.sin(cols / 9.0), np.cos(rows / 7.0), np.sin((rows + cols) / 13.0)], axis=2).astype(np.float32)
    angle = 3.0
    before = straighten_image(display(scene, *old).copy(), angle)
    _, new_angle = reorient(None, angle, old, new)
    after = straighten_image(display(scene, *new).copy(), new_angle)
    expected = display(undisplay(before, *old), *new)      # the same picture, only turned / mirrored
    assert after.shape == expected.shape
    inner = (slice(8, -8), slice(8, -8))
    assert np.abs(after[inner] - expected[inner]).max() < 0.05
