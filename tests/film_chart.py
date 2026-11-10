# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
"""A ColorChecker 24 'photographed on film' with the synthetic film + camera model (shared by tests)."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent / "audit"))
from audit_color import LIGHTS, STOCKS, expose  # noqa: E402

from smneg import film_profile as fp  # noqa: E402

CHART_REFLECTANCE = np.clip(
    fp.lab_to_xyz(fp.reference_lab_d65(), fp._D65) @ np.linalg.inv(fp._SRGB_TO_XYZ_D65).T, 0.003, 1.0)


def chart_negative(stock="Portra-like", light="D65", ev=0.0, h=400, w=600):
    """Returns (raw linear scan, 24 patch centres (x, y), true film base, patch pitch)."""
    refl = np.full((h, w, 3), 0.18)
    ph, pw = h // 6, w // 8
    centres = []
    for i in range(24):
        r, c = divmod(i, 6)
        y0, x0 = h // 6 + r * ph, w // 8 + c * pw
        refl[y0 + 3:y0 + ph - 3, x0 + 3:x0 + pw - 3] = CHART_REFLECTANCE[i]
        centres.append((x0 + pw / 2, y0 + ph / 2))
    rebate = np.zeros((h, w), bool)
    rebate[:12] = rebate[-12:] = True
    raw = expose(refl, rebate, STOCKS[stock], LIGHTS[light], ev)
    return raw, np.array(centres), np.median(raw[rebate], axis=0), pw
