# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
"""16-bit TIFF input keeps its precision; 8-bit input and EXIF orientation behave as before."""
import cv2
import numpy as np
import pytest
from PIL import Image, ImageOps

from smneg import engine


def write_tiff16(path, rgb):
    assert cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))


def test_tiff16_keeps_16_bit_precision(tmp_path):
    rgb = np.full((40, 60, 3), (10000, 20000, 30000), dtype=np.uint16)
    rgb[0, 0] = (10001, 20001, 30001)            # one 16-bit step above its neighbour
    path = tmp_path / "scan16.tif"
    write_tiff16(path, rgb)
    values = engine.decode_negative(str(path), full_resolution=True)
    assert values.shape == (40, 60, 3) and values.dtype == np.float32
    np.testing.assert_allclose(values[1, 1], np.array([10000, 20000, 30000]) / 65535.0, rtol=0, atol=1e-7)
    assert values[0, 0, 0] != values[1, 1, 0]    # 8-bit decoding merged these two values
    assert values[0, 0, 0] == pytest.approx(10001 / 65535.0, abs=1e-7)


def test_tiff16_preview_is_reduced(tmp_path):
    rgb = np.random.default_rng(0).integers(0, 65535, (2000, 3000, 3), dtype=np.uint16)
    path = tmp_path / "big16.tif"
    write_tiff16(path, rgb)
    preview = engine.decode_negative(str(path), full_resolution=False)
    assert max(preview.shape[:2]) == 1600 and preview.max() <= 1.0


def test_tiff8_still_uses_the_8_bit_path(tmp_path):
    rgb = np.random.default_rng(1).integers(0, 255, (30, 50, 3), dtype=np.uint8)
    path = tmp_path / "scan8.tif"
    Image.fromarray(rgb).save(path)
    values = engine.decode_negative(str(path), full_resolution=True)
    np.testing.assert_array_equal(values, rgb.astype(np.float32) / 255.0)


@pytest.mark.parametrize("orientation", range(1, 9))
def test_apply_orientation_matches_pillow(orientation):
    rgb = np.random.default_rng(2).integers(0, 255, (7, 11, 3), dtype=np.uint8)
    image = Image.fromarray(rgb)
    image.getexif()[274] = orientation
    expected = np.asarray(ImageOps.exif_transpose(image))
    np.testing.assert_array_equal(engine.apply_orientation(rgb, orientation), expected)


def test_tiff16_orientation_is_applied(tmp_path):
    tifffile = pytest.importorskip("tifffile")
    rgb = np.random.default_rng(3).integers(0, 65535, (20, 30, 3), dtype=np.uint16)
    path = tmp_path / "rotated16.tif"
    tifffile.imwrite(path, rgb, photometric="rgb", extratags=[(274, "H", 1, 6, False)])
    values = engine.decode_negative(str(path), full_resolution=True)
    np.testing.assert_allclose(values, np.rot90(rgb, -1) / 65535.0, atol=1e-7)
