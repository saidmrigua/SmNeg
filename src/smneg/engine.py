# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import rawpy
from PIL import Image, ImageOps

from .flat_field import RAW_EXTENSIONS, apply_flat_field


def decode_negative(source_path: str, full_resolution: bool) -> np.ndarray:
    path = Path(source_path)
    ext = path.suffix.lower()
    if ext in RAW_EXTENSIONS:
        with rawpy.imread(str(path)) as raw:
            decoded = raw.postprocess(
                half_size=not full_resolution,
                output_bps=16,
                gamma=(1, 1),
                no_auto_bright=True,
                use_auto_wb=False,
                use_camera_wb=False,
                user_wb=[1, 1, 1, 1],
                output_color=rawpy.ColorSpace.raw,
                # LibRaw's default (0.75) may switch the scale to the image's own maximum, so one frame of
                # a roll can decode brighter than the others (measured: +11 % on a Z8 scan). 0 keeps every
                # frame on the camera's white level.
                adjust_maximum_thr=0.0,
            )
        h, w = decoded.shape[:2]
        if full_resolution:
            # a resize to the same size was just a copy; this gives the exact same result, faster
            values = decoded.astype(np.float32) / 65535.0
        else:
            scale = min(1.0, 1600 / max(w, h))
            size = (max(1, int(w * scale)), max(1, int(h * scale)))
            values = np.stack([
                np.asarray(Image.fromarray(decoded[:, :, i]).resize(size, Image.Resampling.BILINEAR), dtype=np.float32) / 65535.0
                for i in range(3)
            ], axis=2)
    else:
        values = _decode_tiff_16bit(path, full_resolution) if ext in (".tif", ".tiff") else None
        if values is None:
            with Image.open(str(path)) as img:
                rgb = ImageOps.exif_transpose(img).convert("RGB")
                if not full_resolution:
                    rgb.thumbnail((1600, 1600))
                values = np.asarray(rgb, dtype=np.float32) / 255.0
    return values


def apply_orientation(pixels: np.ndarray, orientation: int) -> np.ndarray:
    """EXIF orientation 1-8 for an (h, w, c) array; same result as PIL.ImageOps.exif_transpose."""
    if orientation == 2:
        return pixels[:, ::-1]
    if orientation == 3:
        return pixels[::-1, ::-1]
    if orientation == 4:
        return pixels[::-1]
    if orientation == 5:
        return pixels.transpose(1, 0, 2)
    if orientation == 6:
        return np.rot90(pixels, -1)
    if orientation == 7:
        return pixels.transpose(1, 0, 2)[::-1, ::-1]
    if orientation == 8:
        return np.rot90(pixels, 1)
    return pixels


def _decode_tiff_16bit(path: Path, full_resolution: bool) -> np.ndarray | None:
    """16-bit TIFF without quantizing to 8 bits. Returns None for anything else (8-bit, float, unreadable),
    which then goes through the unchanged Pillow path."""
    try:
        encoded = np.fromfile(str(path), dtype=np.uint8)
        pixels = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
        if pixels is None or pixels.dtype != np.uint16:
            return None
        with Image.open(str(path)) as img:
            orientation = int(img.getexif().get(274, 1))
            stored_size = (int(img.tag_v2[256]), int(img.tag_v2[257]))   # (width, height) as stored in the file
    except Exception:
        return None
    if pixels.ndim == 2:
        pixels = np.stack([pixels] * 3, axis=2)
    elif pixels.shape[2] >= 3:
        pixels = pixels[:, :, :3]
    else:
        return None
    pixels = cv2.cvtColor(np.ascontiguousarray(pixels), cv2.COLOR_BGR2RGB)
    # some OpenCV builds already apply the EXIF orientation: only rotate if the stored layout is still unrotated
    if pixels.shape[:2] == (stored_size[1], stored_size[0]):
        pixels = apply_orientation(pixels, orientation)
    pixels = np.ascontiguousarray(pixels)
    if not full_resolution:
        scale = min(1.0, 1600 / max(pixels.shape[:2]))
        if scale < 1.0:
            size = (max(1, int(pixels.shape[1] * scale)), max(1, int(pixels.shape[0] * scale)))
            pixels = cv2.resize(pixels, size, interpolation=cv2.INTER_AREA)
    return pixels.astype(np.float32) / 65535.0


def tone_curve(levels: np.ndarray, profile: str) -> np.ndarray:
    if profile == "Flat":
        return 0.12 + 0.76 * levels
    return 0.35 * levels + 0.65 * (3 * levels**2 - 2 * levels**3)


def source_max_edge(source_path: str) -> int | None:
    """Longest side (in pixels) of the source image without decoding the RAW. Used to estimate 100% before the full-size image arrives."""
    path = Path(source_path)
    try:
        if path.suffix.lower() in RAW_EXTENSIONS:
            with rawpy.imread(str(path)) as raw:
                return max(raw.sizes.width, raw.sizes.height)
        with Image.open(str(path)) as img:
            return max(img.size)
    except Exception:
        return None


class OfficialFilmEngine:
    PARALLEL_MIN_PIXELS = 4_000_000   # below this size (previews) sequential computation is enough
    # last error per file (shown to the user); does not affect the inversion computation
    errors: dict = {}

    @staticmethod
    def _invert_channel(values, inner, window, channel):
        """Inversion of a single channel (formula unchanged). Intermediate operations are in-place to save memory."""
        y_start, y_end, x_start, x_end = window
        base = max(float(np.percentile(inner[:, :, channel], 99.5)), 1e-6)
        density = values[:, :, channel] / base
        np.clip(density, 1e-4, 1.0, out=density)
        np.log10(density, out=density)
        np.negative(density, out=density)
        region = density[y_start:y_end, x_start:x_end]
        if region.size == 0:
            region = density
        low, high = np.percentile(region, [0.5, 99.5])
        return np.clip((density - low) / max(high - low, 1e-6), 0, 1)

    @staticmethod
    def load_negative_base(
        source_path: str, full_resolution: bool = False, flat_field: np.ndarray | None = None
    ) -> Optional[np.ndarray]:
        OfficialFilmEngine.errors.pop(source_path, None)
        try:
            values = decode_negative(source_path, full_resolution)
            if flat_field is not None:
                values = apply_flat_field(values, flat_field)

            # density is computed from the inner 20%-80% region to avoid the edges
            height, width = values.shape[:2]
            y_start, y_end = int(height * 0.2), max(int(height * 0.8), 1)
            x_start, x_end = int(width * 0.2), max(int(width * 0.8), 1)

            inner = values[y_start:y_end, x_start:x_end]
            if inner.size == 0:
                inner = values

            result = np.empty_like(values)
            window = (y_start, y_end, x_start, x_end)
            if values.shape[0] * values.shape[1] > OfficialFilmEngine.PARALLEL_MIN_PIXELS:
                # the 3 channels are independent, so they are computed concurrently (bit-identical result)
                with ThreadPoolExecutor(max_workers=3) as pool:
                    channels = list(pool.map(
                        lambda channel: OfficialFilmEngine._invert_channel(values, inner, window, channel),
                        range(3)))
            else:
                channels = [OfficialFilmEngine._invert_channel(values, inner, window, channel)
                            for channel in range(3)]
            for channel, plane in enumerate(channels):
                result[:, :, channel] = plane

            return result

        except Exception as e:
            print(f"Error loading {source_path}: {e}")
            OfficialFilmEngine.errors[source_path] = f"{type(e).__name__}: {e}"
            return None

    @staticmethod
    def apply_pipeline(
        base_positive: np.ndarray,
        cyan_points: int,
        magenta_points: int,
        yellow_points: int,
        density_step: int,
        contrast: float,
        saturation: float,
        rotation: int,
        mirror: bool,
        auto_crop: bool,
        show_clipping: bool,
        output_float: bool = False,
    ) -> np.ndarray:
        plane = np.power(base_positive, 1.0 / 1.4)

        c_gain = 2.0 ** (-cyan_points * 0.04)
        m_gain = 2.0 ** (-magenta_points * 0.04)
        y_gain = 2.0 ** (-yellow_points * 0.04)
        d_gain = 2.0 ** (density_step * 0.04)

        plane[:, :, 0] = np.clip(plane[:, :, 0] * c_gain * d_gain, 0.0, 1.0)
        plane[:, :, 1] = np.clip(plane[:, :, 1] * m_gain * d_gain, 0.0, 1.0)
        plane[:, :, 2] = np.clip(plane[:, :, 2] * y_gain * d_gain, 0.0, 1.0)

        if contrast != 1.0:
            plane = np.clip((plane - 0.5) * contrast + 0.5, 0.0, 1.0)

        if saturation != 1.0:
            # saturation in float to keep precision (no banding)
            hsv = cv2.cvtColor(np.ascontiguousarray(plane, dtype=np.float32), cv2.COLOR_RGB2HSV)
            hsv[:, :, 1] = np.clip(hsv[:, :, 1] * saturation, 0.0, 1.0)
            plane = np.clip(cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB), 0.0, 1.0)

        if mirror:
            plane = np.fliplr(plane)

        rot_steps = (rotation % 360) // 90
        if rot_steps > 0:
            plane = np.rot90(plane, -rot_steps)

        if auto_crop:
            ch, cw = plane.shape[:2]
            plane = plane[int(ch * 0.05):int(ch * 0.95), int(cw * 0.05):int(cw * 0.95)]

        if output_float:
            return np.ascontiguousarray(np.clip(plane, 0.0, 1.0), dtype=np.float32)

        out_img = (np.clip(plane, 0.0, 1.0) * 255.0).astype(np.uint8)

        if show_clipping:
            clipped_high = np.all(out_img >= 250, axis=-1)
            out_img[clipped_high] = [255, 0, 0]
            clipped_low = np.all(out_img <= 5, axis=-1)
            out_img[clipped_low] = [0, 0, 255]

        return out_img
