import numpy as np
import pytest
from smneg.engine import decode_negative

tifffile = pytest.importorskip('tifffile')


@pytest.mark.parametrize('full', [False, True])
def test_tiff_keeps_16bit_precision_and_rgb(tmp_path, full):
    pixels = np.array([[[10000, 10001, 50000], [0, 65535, 12345]]], dtype=np.uint16)
    path = tmp_path / 'scan_é.tif'
    tifffile.imwrite(path, pixels, photometric='rgb')
    actual = decode_negative(str(path), full)
    np.testing.assert_allclose(actual, pixels.astype(np.float32) / 65535, rtol=0, atol=0)
    assert actual[0, 0, 0] != actual[0, 0, 1]


@pytest.mark.parametrize('orientation', range(1, 9))
def test_tiff_orientation(tmp_path, orientation):
    from PIL import Image, ImageOps
    pixels = np.arange(18, dtype=np.uint8).reshape(2, 3, 3)
    path = tmp_path / 'oriented.tif'
    tifffile.imwrite(path, pixels, photometric='rgb', extratags=[(274, 'H', 1, orientation, False)])
    with Image.open(path) as image:
        expected = np.asarray(ImageOps.exif_transpose(image).convert('RGB'), dtype=np.float32) / 255
    np.testing.assert_array_equal(decode_negative(str(path), True), expected)
