# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np


@dataclass
class FrameItem:
    index: int
    path: str
    base_positive: np.ndarray
    cyan: int = 0
    magenta: int = 0
    yellow: int = 0
    density: int = 0
    contrast: float = 1.0
    saturation: float = 1.0
    rotation: int = 0
    mirror: bool = False
    auto_crop: bool = False
    show_clipping: bool = False
    is_passed: bool = False
    manual_crop: tuple[float, float, float, float] | None = None
    sharpness: int = 0
    processed_date: str = field(default_factory=lambda: date.today().isoformat())
    straighten: float = 0.0
    tone_profile: str = "Natural"
    # Scientific engine: automatic print exposure and contrast (neutral, per frame); off = flat master
    auto_print: bool = True
    # film base picked by hand (linear RGB of the clear film), scientific engine; None = automatic
    base_pick: list | None = None
    # grey picks (linear scan RGB of areas that should be neutral); two or more at different tones also
    # correct the tilt between the dye layers (cast in the highlights or shadows)
    grey_picks: list | None = None
    # print settings pasted from another frame (scientific engine), so this frame is printed exactly like
    # it: {"anchor": density of mid grey, "bounds": Auto print's ends or None, "balance": grey balance or
    # None}. None = the frame's own metering.
    print_lock: dict | None = None
    # scientific engine: film-base / density statistics of the preview (not saved, recomputed on load)
    stats: object = field(default=None, repr=False, compare=False)
