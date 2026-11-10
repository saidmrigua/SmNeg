# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
import cv2
import numpy as np


# camera RAW formats decoded by LibRaw (rawpy): Nikon, Fujifilm, Adobe DNG, Canon, Sony, Olympus/OM,
# Panasonic/Leica, Pentax, Samsung, Hasselblad, Phase One, Leica, Kodak, Mamiya, Sigma
RAW_EXTENSIONS = {
    ".nef", ".nrw", ".raf", ".dng", ".cr2", ".cr3", ".crw", ".arw", ".srf", ".sr2", ".orf", ".rw2", ".raw",
    ".rwl", ".pef", ".srw", ".3fr", ".fff", ".iiq", ".erf", ".kdc", ".dcr", ".mos", ".mef", ".x3f",
}


def build_flat_field(reference: np.ndarray) -> np.ndarray:
    height, width = reference.shape[:2]
    if np.any(np.mean(reference >= 0.999, axis=(0, 1)) > 0.01):
        raise ValueError("The reference RAW is overexposed in at least one channel.")
    scale = min(1.0, 256 / max(height, width))
    sampled = cv2.resize(reference, (max(1, round(width * scale)), max(1, round(height * scale))),
                         interpolation=cv2.INTER_AREA)
    field = cv2.GaussianBlur(sampled, (0, 0), sigmaX=2)
    level = np.median(field, axis=(0, 1))
    if np.any(level < 0.01) or np.any(field < level * 0.1):
        raise ValueError("The reference is too dark or partially obstructed.")
    return level / field


def apply_flat_field(values: np.ndarray, gain: np.ndarray) -> np.ndarray:
    height, width = values.shape[:2]
    gain_height, gain_width = gain.shape[:2]
    if abs((width / height) / (gain_width / gain_height) - 1) > 0.02:
        raise ValueError("The RAW framing does not match the flat-field reference.")
    corrected = cv2.resize(gain, (width, height), interpolation=cv2.INTER_LINEAR)
    np.multiply(corrected, values, out=corrected)
    return corrected
