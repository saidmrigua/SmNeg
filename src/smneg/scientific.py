# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
"""Scientific inversion engine: film base -> density -> roll-level neutral balance -> print -> sRGB.

Every step has a physical meaning:

1. The scan is linear camera RGB (``engine.decode_negative``), optionally flat-fielded.
2. The **film base** (unexposed film, orange mask) is measured: the rebate when it is visible,
   otherwise the clearest part of the image. Density above base: ``D = -log10(v / base)``.
3. The three dye layers have different contrasts (gammas) in camera RGB. Their ratio is a property of
   the film + light + camera, not of the picture, so it is estimated over the **whole roll**
   (pooled histograms). Neutral greys then have equal channel densities, whatever is in the frame.
4. Density is converted back to relative scene log exposure (``/ gamma``), anchored by one scalar
   exposure (auto-metered, partially), so a mid grey lands at 18 %.
5. Printer lights (C/M/Y/D) are offsets in log exposure, 1 point = 0.025 log E (1/12 stop).
6. Output is scene-referred linear light with a soft highlight shoulder, encoded as sRGB
   (exports carry an sRGB ICC profile).

All arrays are float32 0..1 (linear) until the final encoding.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .engine import OfficialFilmEngine, decode_negative
from .flat_field import apply_flat_field

POINT = 0.025                      # log10 exposure per printer point (1/12 stop)
FILM_GAMMA = 0.60                  # typical C-41 green gamma in camera RGB
MID_GREY = 0.18
BIN_WIDTH = 0.005                  # density histogram resolution
N_BINS = 1000                      # 0 .. 5.0 absolute density
SATURATED = 0.95                   # linear value treated as clipped
MAX_DENSITY_ABOVE_BASE = 2.8       # denser than this: holder / tape, not image
DENSE = 1.0                        # green density above base from which the holder test applies
METER_WINDOW = (0.2, 0.8)          # statistics come from the centre of the scan (rebate, holes and holder are at the edges)
METER_PULL = 0.7                   # 1 = full per-frame auto exposure, 0 = roll exposure only
SLOPE_QUANTILES = (80.0, 98.0)
SAMPLE_COUNT = 20000               # film pixels kept per frame for metering with a film profile     # density quantiles used for the dye-gamma ratios

PROFILES = {
    # name: (log contrast, shoulder start, toe lift)
    "Natural": (1.00, 0.80, 0.0),
    "Flat": (0.85, 0.70, 0.004),
    "S Curve": (1.25, 0.75, 0.0),
}


@dataclass
class FrameStats:
    """Measured once from the preview of a frame (independent of the user's settings)."""
    base: np.ndarray        # (3,) linear film-base estimate for this frame
    source: str             # "rebate" | "clear area" | "estimate" | "picked" (by hand)
    hist: np.ndarray        # (3, N_BINS) histograms of absolute density -log10(v), film area only
    mono: bool = False      # B&W negative (no orange mask)
    samples: np.ndarray | None = None   # (n, 3) absolute densities of film pixels (metering with a film profile)


@dataclass
class RollModel:
    """Parameters shared by every frame of a roll."""
    base: np.ndarray        # (3,) linear
    slopes: np.ndarray      # (3,) multiply densities so neutral greys get equal values (green = 1)
    meter: float            # roll-median green density above base (exposure reference)
    frames: int = 0
    luma_ends: np.ndarray | None = None    # (2,) roll's shadow / highlight ends of brightness (all frames pooled)
    colour_ends: np.ndarray | None = None  # (2, 3) each channel's ends relative to brightness (median of the frames)


@dataclass
class FrameParams:
    base: np.ndarray
    slopes: np.ndarray
    anchor: float           # green-equivalent density that maps to 18 % grey
    gamma: float = FILM_GAMMA
    mono: bool = False
    crosstalk: np.ndarray | None = None   # film profile: 3x3 unmix applied to density above base
    balance: tuple | None = None          # from grey picks: (slope R, offset R, slope B, offset B) on density
    bounds: np.ndarray | None = None      # Auto print: (2, 3) shadow and highlight ends per channel, in balanced density
    print_paper: bool = False             # Auto print: render through the paper curve (toe + shoulder)


# ----------------------------------------------------------------------------- loading
DISPLAY_ENCODED = {".jpg", ".jpeg", ".png"}


def is_display_encoded(path: str) -> bool:
    """JPEG, PNG and 8-bit TIFF scans hold sRGB-encoded values, not linear light (as NegPy and most
    tools assume for untagged 8-bit files). 16-bit TIFF and RAW are linear."""
    ext = Path(path).suffix.lower()
    if ext in DISPLAY_ENCODED:
        return True
    if ext in (".tif", ".tiff"):
        try:
            import tifffile
            with tifffile.TiffFile(path) as tif:
                return tif.pages[0].dtype == np.uint8
        except Exception:   # unreadable here: the decoder reports the real error
            return False
    return False


def srgb_decode(values: np.ndarray) -> np.ndarray:
    v = np.clip(values, 0.0, 1.0)
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4).astype(np.float32)


def load_linear(path: str, full_resolution: bool = False, flat_field: np.ndarray | None = None):
    """Linear scan values (float32), flat-fielded. None on failure (reason in OfficialFilmEngine.errors)."""
    OfficialFilmEngine.errors.pop(path, None)
    try:
        values = decode_negative(path, full_resolution)
        if is_display_encoded(path):
            values = srgb_decode(values)
        if flat_field is not None:
            values = apply_flat_field(values, flat_field)
        return np.ascontiguousarray(values, dtype=np.float32)
    except Exception as error:  # same contract as load_negative_base: report, do not crash the UI
        OfficialFilmEngine.errors[path] = f"{type(error).__name__}: {error}"
        return None


# ----------------------------------------------------------------------------- film base
def _blocks(log_values: np.ndarray, size: int):
    h, w = log_values.shape[:2]
    hb, wb = h // size, w // size
    cube = log_values[:hb * size, :wb * size].reshape(hb, size, wb, size, 3)
    return cube.mean((1, 3)), cube.std((1, 3)).max(-1), hb, wb


REBATE_EDGE = 0.15             # a rebate lies within this fraction of a side
REBATE_LENGTH = 0.30           # ... and runs along at least this fraction of that side
REBATE_COLOUR_TOLERANCE = 0.15  # a frame rebate may differ from the roll base mainly in brightness (log10); measured: real 0.09, false 0.22-0.38


def _is_rebate_strip(ys, xs, hb, wb) -> bool:
    """The clearest uniform blocks form a rebate when they run as a strip along one side of the frame,
    not when they are a few bright patches of the picture (a wall, a sky) that happen to touch an edge."""
    if len(ys) < 3:
        return False
    for along, across, length, depth in ((xs, ys, wb, hb), (ys, xs, hb, wb)):
        for side in (across < depth * REBATE_EDGE, across > depth * (1 - REBATE_EDGE)):
            if side.any() and len(np.unique(along[side])) >= REBATE_LENGTH * length:
                return True
    return False


def estimate_base(values: np.ndarray, light: np.ndarray | None = None) -> tuple[np.ndarray, str]:
    """Film base (orange mask) of one scan.

    Looks for large uniform areas that are the clearest film in the frame: the rebate between frames
    or around the image. Bare light (no film) is rejected because it has no orange mask: compared with
    film, its blue is much stronger relative to red. ``light`` (the flat-field light colour), when known,
    makes that test exact.
    """
    v = np.asarray(values, dtype=np.float32)
    h, w = v.shape[:2]
    logv = np.log10(np.clip(v, 1e-5, None))
    clipped = v.max(-1) >= SATURATED
    size = max(8, min(h, w) // 60)
    means, stds, hb, wb = _blocks(logv, size)
    sat_blocks = clipped[:hb * size, :wb * size].reshape(hb, size, wb, size).mean((1, 3)) > 0.01
    smooth = (stds < 0.025) & ~sat_blocks

    # orange-ness: log B - log R (relative to the light when it is known)
    reference = np.log10(np.clip(light, 1e-5, None)) if light is not None else np.zeros(3)
    orange = (means[..., 2] - reference[2]) - (means[..., 0] - reference[0])
    film_orange = np.median((logv[..., 2] - reference[2] - logv[..., 0] + reference[0])[~clipped]) \
        if np.any(~clipped) else 0.0
    limit = -0.15 if light is not None else film_orange + 0.30
    bare = orange > limit
    # brighter than the film in every channel and not orange: bare light seen through the holder
    candidates = smooth & ~bare
    if candidates.sum() >= 3:
        pts = means[candidates]
        g = pts[:, 1]
        top = pts[g >= np.percentile(g, 98) - 0.03]
        top = top[top[:, 1] >= g.max() - 0.04]
        ys, xs = np.nonzero(candidates)
        sel = g >= g.max() - 0.04
        source = "rebate" if _is_rebate_strip(ys[sel], xs[sel], hb, wb) else "clear area"
        return (10 ** np.median(top, axis=0)).astype(np.float32), source

    # fallback: the clearest 0.1 % of film pixels (same pixels for all channels)
    ok = ~clipped & ~((logv[..., 2] - logv[..., 0]) > limit)
    flat = logv[ok] if np.any(ok) else logv.reshape(-1, 3)
    luma = flat.sum(-1)
    n = max(20, int(luma.size * 0.001))
    idx = np.argpartition(luma, -n)[-n:] if luma.size > n else np.arange(luma.size)
    return (10 ** np.median(flat[idx], axis=0)).astype(np.float32), "estimate"


def measure_film_base(scans: list[np.ndarray]) -> tuple[np.ndarray, float, float]:
    """Film base from scans of clear (unexposed) film, such as the leader of the roll.

    The central 60 % of each scan, clipped pixels excluded, median per channel, then the median of the
    scans. Returns (base, unevenness, orange) where unevenness is the spread (log10) inside the scans,
    which should be small on clear film, and orange is log B - log R (below ORANGE_MASK on colour film)."""
    bases, spreads = [], []
    for values in scans:
        v = np.asarray(values, np.float32)
        h, w = v.shape[:2]
        centre = v[int(h * 0.2):max(int(h * 0.8), 1), int(w * 0.2):max(int(w * 0.8), 1)].reshape(-1, 3)
        centre = centre[centre.max(-1) < SATURATED]
        if len(centre) < 100:
            raise ValueError("The scan of the clear film is clipped: lower the exposure.")
        logs = np.log10(np.clip(centre, 1e-5, None))
        bases.append(np.median(centre, axis=0))
        spreads.append(float(np.max(np.percentile(logs, 95, axis=0) - np.percentile(logs, 5, axis=0))))
    base = np.median(np.array(bases), axis=0).astype(np.float32)
    orange = float(np.log10(base[2]) - np.log10(base[0]))
    return base, float(max(spreads)), orange


# ----------------------------------------------------------------------------- statistics
def is_monochrome(values: np.ndarray) -> bool:
    """B&W negative: no orange mask, so blue/red log ratio hardly varies over the frame."""
    v = np.asarray(values, dtype=np.float32).reshape(-1, 3)
    v = v[v.max(-1) < SATURATED]
    if len(v) < 100:
        return False
    o = np.log10(np.clip(v[:, 2], 1e-5, None)) - np.log10(np.clip(v[:, 0], 1e-5, None))
    p10, p90 = np.percentile(o, [10, 90])
    g = np.log10(np.clip(v[:, 1], 1e-5, None)) - np.log10(np.clip(v[:, 0], 1e-5, None))
    q10, q90 = np.percentile(g, [10, 90])
    return (p90 - p10) < 0.12 and (q90 - q10) < 0.12


def film_mask(values: np.ndarray, base: np.ndarray, mono: bool = False) -> np.ndarray:
    """Pixels that are image on film: not clipped, not clearer than the base, not opaque holder,
    and (colour film) carrying the orange mask. Bare light and the holder have no orange mask."""
    v = np.asarray(values, dtype=np.float32)
    above = np.log10(base) - np.log10(np.clip(v, 1e-5, None))
    ok = (v.max(-1) < SATURATED) & np.all(above > -0.05, -1) & (above[..., 1] < MAX_DENSITY_ABOVE_BASE)
    if not mono:
        base_orange = np.log10(base[2]) - np.log10(base[0])
        orange = np.log10(np.clip(v[..., 2], 1e-5, None)) - np.log10(np.clip(v[..., 0], 1e-5, None))
        ok &= orange < base_orange + 0.35
        # dense film is more orange than the base (the blue layer is the densest); a dense pixel that is
        # less orange is the opaque holder or mask, whose three channels all sit at the sensor's floor
        ok &= ~((above[..., 1] > DENSE) & (orange > base_orange + 0.10))
    return ok


ORANGE_MASK = -0.15        # log B - log R of the base below this: colour negative (orange mask)


def frame_stats(values: np.ndarray, light: np.ndarray | None = None) -> FrameStats:
    base, source = estimate_base(values, light)
    # a frame with little colour (a sky, fog) is not B&W when its film base carries the orange mask
    mono = is_monochrome(values) and float(np.log10(base[2]) - np.log10(base[0])) > ORANGE_MASK
    h, w = values.shape[:2]
    lo, hi = METER_WINDOW
    inner = np.asarray(values[int(h * lo):max(int(h * hi), 1), int(w * lo):max(int(w * hi), 1)],
                       dtype=np.float32).reshape(-1, 3)
    dabs = -np.log10(np.clip(inner, 1e-5, None))
    film = film_mask(inner, base, mono)
    if film.sum() < 100:
        film = np.ones(len(dabs), bool)
    hist = np.stack([np.histogram(dabs[film, c], bins=N_BINS, range=(0, N_BINS * BIN_WIDTH))[0]
                     for c in range(3)]).astype(np.int64)
    picked = dabs[film]
    if len(picked) > SAMPLE_COUNT:
        picked = picked[np.random.default_rng(0).choice(len(picked), SAMPLE_COUNT, replace=False)]
    return FrameStats(base=base, source=source, hist=hist, mono=mono, samples=picked.astype(np.float32))


def _unmixed_median(stats: FrameStats, base: np.ndarray, crosstalk: np.ndarray) -> float:
    """Median green density above base after the film profile's crosstalk unmix."""
    density = stats.samples + np.log10(base).astype(np.float32)          # above base
    return float(np.median(density @ np.asarray(crosstalk, np.float32)[1]))


def _percentile_from_hist(hist: np.ndarray, q: float) -> float:
    total = hist.sum()
    if total == 0:
        return 0.0
    cdf = np.cumsum(hist) / total
    target = q / 100.0
    i = min(int(np.searchsorted(cdf, target)), len(hist) - 1)
    below = cdf[i - 1] if i else 0.0
    inside = (target - below) / max(cdf[i] - below, 1e-12)      # linear inside the bin
    return (i + float(np.clip(inside, 0.0, 1.0))) * BIN_WIDTH


def _shift(hist: np.ndarray, density: float) -> np.ndarray:
    """Histogram of (absolute density - density), i.e. density above a base (fractional bins)."""
    position = density / BIN_WIDTH
    k = int(np.floor(position))
    frac = position - k

    def whole(n):
        out = np.zeros(len(hist), np.float64)
        if abs(n) >= len(hist):      # shifted entirely out of range (e.g. a black, unexposed frame)
            return out
        if n >= 0:
            out[:len(hist) - n] = hist[n:]
        else:
            out[-n:] = hist[:len(hist) + n]
        return out

    return (1 - frac) * whole(k) + frac * whole(k + 1)


def roll_model(stats: list[FrameStats], film=None, reference: np.ndarray | None = None) -> RollModel | None:
    """Base, dye-gamma ratios and exposure reference of a roll (colour frames; B&W frames are separate).
    With a film profile the exposure reference is measured on the unmixed densities. ``reference`` is a
    film base measured on scans of clear film (the roll's leader): it becomes the roll's base."""
    if not stats:
        return None
    colour = [s for s in stats if not s.mono]
    stats = colour or stats
    picked = [s.base for s in stats if s.source == "picked"]
    rebates = [s.base for s in stats if s.source == "rebate"]
    if reference is not None:   # scans of the clear film: the most direct measurement
        base = np.asarray(reference, np.float64)
    elif picked:    # a base clicked by the user wins over automatic detection
        base = np.median(picked, axis=0)
    elif rebates:
        base = np.median(rebates, axis=0)
    else:  # clearest film over the whole roll (robust: 90th percentile of the frames' candidates)
        bases = np.array([s.base for s in stats])
        order = np.argsort(np.log10(bases).sum(-1))
        base = bases[order[int(round((len(order) - 1) * 0.9))]]
    pooled = np.zeros((3, N_BINS), np.float64)
    meters = []
    for s in stats:
        own = frame_base(s, base)
        dbase = -np.log10(own)
        shifted = np.stack([_shift(s.hist[c], dbase[c]) for c in range(3)])
        pooled += shifted
        if film is not None and s.samples is not None:
            meters.append(_unmixed_median(s, own, film.matrix_array))
        else:
            meters.append(_percentile_from_hist(s.hist[1], 50) - dbase[1])   # exact (no bin shift)
    slopes = dye_slopes(pooled)
    model = RollModel(base=np.asarray(base, np.float32), slopes=slopes, meter=float(np.median(meters)),
                      frames=len(stats))
    lumas, colours = [], []
    for s in stats:      # the roll's print range (Auto print with the Balanced or Roll meter)
        if s.samples is None or len(s.samples) < 100 or s.mono:
            continue
        zero = FrameParams(base=np.asarray(frame_base(s, base), np.float32),
                           slopes=film.slopes_array if film is not None else slopes, anchor=0.0,
                           crosstalk=film.matrix_array if film is not None else None)
        _, colour, luma = print_ends(s.samples, zero, film is not None)
        lumas.append(luma)
        colours.append(colour)
    if lumas:
        model.luma_ends = np.percentile(np.concatenate(lumas), PRINT_ENDS).astype(np.float64)
        model.colour_ends = np.median(np.array(colours), axis=0)
    return model


def dye_slopes(pooled: np.ndarray) -> np.ndarray:
    """Ratios of the dye-layer contrasts (green = 1), from the roll's density distributions.

    Neutral greys have densities proportional to each layer's gamma, so the quantiles of the
    three channels are (on average over a roll) proportional too. A least-squares fit through the
    origin over the quantiles in SLOPE_QUANTILES ignores the extreme tail (holder edges, specks)."""
    qs = np.linspace(SLOPE_QUANTILES[0], SLOPE_QUANTILES[1], 25)
    Q = np.array([[_percentile_from_hist(pooled[c], q) for c in range(3)] for q in qs])
    g = Q[:, 1]
    slopes = np.array([np.dot(g, Q[:, c]) / max(np.dot(Q[:, c], Q[:, c]), 1e-9) for c in range(3)])
    return np.clip(slopes, 0.5, 2.0).astype(np.float32)


def frame_base(stats: FrameStats, roll_base: np.ndarray) -> np.ndarray:
    """A frame uses its own rebate when it shows one (protects against scan-exposure changes),
    and B&W frames always use their own base; otherwise the roll's base.

    A detected rebate whose colour differs from the roll's base by more than a uniform brightness change
    (a different scan exposure) is not trusted: the roll's base (or the film base reference) is used."""
    if stats.source == "picked" or stats.mono:
        return stats.base
    if stats.source == "rebate":
        difference = np.log10(np.asarray(stats.base, np.float64)) - np.log10(np.asarray(roll_base, np.float64))
        if np.ptp(difference) <= REBATE_COLOUR_TOLERANCE:
            return stats.base
    return roll_base


PICK_TONE_GAP = 0.15           # grey picks this far apart in density also correct the tilt (not only the offset)
PICK_TONE_GAP_PRINT = 0.10     # the same, in the normalized print range (Auto print)
PICK_TILT_LIMITS = (0.7, 1.4)


def grey_balance(picks, params: FrameParams) -> tuple:
    """Neutral balance from grey picks (linear scan RGB of areas that should be grey).

    One pick fixes an offset. Picks at different tones (a light grey and a dark grey) also fix the tilt of
    the red and blue layers against green, which is what removes a cast that grows towards the highlights
    or the shadows. Least squares on green-equivalent density: R·s + o = G (and the same for B).
    Returns (slope R, offset R, slope B, offset B)."""
    flat = FrameParams(base=params.base, slopes=params.slopes, anchor=0.0, crosstalk=params.crosstalk,
                       bounds=params.bounds)
    density = balanced_density(np.asarray(picks, np.float32)[None], flat)[0].astype(np.float64)
    gap = PICK_TONE_GAP if params.bounds is None else PICK_TONE_GAP_PRINT
    green = density[:, 1]
    out = []
    for c in (0, 2):
        channel = density[:, c]
        slope = 1.0
        if len(picks) >= 2 and np.ptp(green) >= gap and np.ptp(channel) > 1e-3:
            slope = float(np.clip(np.polyfit(channel, green, 1)[0], *PICK_TILT_LIMITS))
        out += [slope, float(np.mean(green - slope * channel))]
    return tuple(out)


METER_STRENGTHS = {"frame": 1.0, "balanced": 0.5, "roll": 0.0}   # how much Auto print follows each frame


def frame_params(stats: FrameStats, roll: RollModel, film=None, auto_print: bool = False,
                 meter: float = 1.0, grey_picks=None) -> FrameParams:
    """``film`` (a FilmProfile) replaces the estimated dye slopes and contrast by measured ones.
    ``auto_print`` normalizes each channel between its shadow and highlight ends; ``meter`` says how much
    those ends follow the frame (1) or the whole roll (0: one print setting for the roll, like a lab's lock)."""
    params = _frame_params(stats, roll, film)
    if auto_print and stats.samples is not None and len(stats.samples) >= 100:
        luma, colour, _ = print_ends(stats.samples, params, film is not None or params.mono)
        if roll.luma_ends is not None and meter < 1.0 and not params.mono:
            # exposure and contrast (brightness ends) and colour (channel ends) are blended with the roll's:
            # the roll's colour is the median of its frames, so one strongly coloured frame cannot tint it
            luma = roll.luma_ends + meter * (luma - roll.luma_ends)
            colour = roll.colour_ends                    # colour belongs to the film: always the roll's
        params.bounds = luma[:, None] + colour
        params.print_paper = True
    if grey_picks and len(grey_picks) >= 2 and not params.mono:
        params.balance = grey_balance(grey_picks, params)
    return params


def _frame_params(stats: FrameStats, roll: RollModel, film=None) -> FrameParams:
    base = frame_base(stats, roll.base)
    own = _percentile_from_hist(stats.hist[1], 50) + float(np.log10(base[1]))   # median density above base
    if stats.mono:  # no roll colour model for silver images: neutral by construction, own exposure
        return FrameParams(base=np.asarray(base, np.float32), slopes=np.ones(3, np.float32),
                           anchor=float(own), mono=True)
    pull = METER_PULL
    anchor = roll.meter + pull * (own - roll.meter)
    if film is not None:
        if stats.samples is not None:
            own = _unmixed_median(stats, base, film.matrix_array)
            anchor = roll.meter + pull * (own - roll.meter)
        return FrameParams(base=np.asarray(base, np.float32), slopes=film.slopes_array, anchor=float(anchor),
                           gamma=float(film.gamma), crosstalk=film.matrix_array)
    return FrameParams(base=np.asarray(base, np.float32), slopes=roll.slopes, anchor=float(anchor))


# ----------------------------------------------------------------------------- rendering
def balanced_density(values: np.ndarray, params: FrameParams) -> np.ndarray:
    """Density above the film base per channel, dye crosstalk unmixed (film profile) and scaled by the dye
    slopes, so a neutral grey has (about) equal values. With Auto print it is then normalized to the print
    range: 0 = shadow end, 1 = highlight end of each channel."""
    v = np.asarray(values, dtype=np.float32)
    out = np.empty(v.shape, np.float32)
    for c in range(3):
        plane = out[..., c]
        np.divide(v[..., c], params.base[c], out=plane)
        np.clip(plane, 1e-5, None, out=plane)
        np.log10(plane, out=plane)                     # = -density above base
    if params.crosstalk is not None:                   # film profile: unmix the dye densities
        np.negative(out, out=out)
        out[...] = out @ np.asarray(params.crosstalk, np.float32).T
        np.negative(out, out=out)
    for c in range(3):
        plane = out[..., c]
        plane *= -params.slopes[c]                     # green-equivalent density
        if params.bounds is not None:
            plane -= np.float32(params.bounds[0][c])
            plane /= np.float32(max(params.bounds[1][c] - params.bounds[0][c], 1e-3))
    return out


def scene_log_exposure(values: np.ndarray, params: FrameParams) -> np.ndarray:
    """log10 of relative exposure per channel (0 = mid grey): the scene's for the flat master, the print's
    with Auto print."""
    out = balanced_density(values, params)
    if params.balance is not None:                     # grey picks: tilt and offset of R and B against G
        for c in (0, 2):
            out[..., c] *= np.float32(params.balance[c])
            out[..., c] += np.float32(params.balance[c + 1])
    if params.mono:  # silver is neutral: one density for all channels
        out[...] = out.mean(-1, keepdims=True)
    if params.bounds is not None:
        # Auto print tone: the normalized density is shown through a 1/1.4 power as display value (the
        # Classic engine's rendering, which keeps open shadows and bright mid-tones), here with the same
        # ends for a neutral grey in the three channels. Expressed as log exposure for the printer lights.
        np.clip(out, 1e-4, 4.0, out=out)
        np.power(out, np.float32(1.0 / PRINT_POWER), out=out)
        linear = np.where(out <= 0.04045, out / 12.92, np.power((out + 0.055) / 1.055, 2.4)).astype(np.float32)
        out = np.log10(linear / MID_GREY)
    else:
        out -= np.float32(params.anchor)
        out /= np.float32(params.gamma)
    # far beyond white there is no picture (opaque holder, mask): its channels differ only because the
    # film base does, which would print as a strong false colour. Colour fades to neutral there.
    luma = (out @ PRINT_LUMA)[..., None]
    keep = np.clip((BEYOND_WHITE[1] - luma) / (BEYOND_WHITE[1] - BEYOND_WHITE[0]), 0.0, 1.0)
    out -= luma
    out *= keep
    out += luma
    return out


# ----------------------------------------------------------------------------- auto print
PAPER_WHITE = float(np.log10(0.90 / 0.18))     # paper white (L* ~96), log10 relative to mid grey
PAPER_BLACK = float(np.log10(0.004 / 0.18))    # paper black (Dmax ~2.4, L* ~3.6)
PAPER_SHOULDER, PAPER_TOE = 6.0, 6.0           # knee sharpness (per decade)
BEYOND_WHITE = (PAPER_WHITE + 0.15, PAPER_WHITE + 0.55)   # log exposure where colour fades to neutral
PRINT_ENDS = (0.5, 99.5)      # film-pixel percentiles taken as shadow and highlight ends
PRINT_POWER = 1.4             # display value = normalized density ** (1 / 1.4), as in the Classic engine
PRINT_LUMA = np.array([0.25, 0.5, 0.25], np.float32)


def print_ends(samples: np.ndarray, params: FrameParams, shared: bool):
    """Shadow and highlight ends (0.5 / 99.5 % of the film pixels) of balanced density.

    Returns (brightness ends (2,), each channel's ends relative to them (2, 3), the densities' luma).
    The per-channel part also absorbs what a single film base cannot: a slightly different minimum density
    in each layer and scanner flare, which otherwise tint the highlights. ``shared`` (film profile, B&W)
    trusts the measured balance: no per-channel part."""
    flat = FrameParams(base=params.base, slopes=params.slopes, anchor=0.0, crosstalk=params.crosstalk)
    density = balanced_density(np.power(np.float32(10.0), -samples)[None], flat)[0]
    luma = density @ PRINT_LUMA
    luma_ends = np.percentile(luma, PRINT_ENDS).astype(np.float64)
    if shared:
        return luma_ends, np.zeros((2, 3)), luma
    return luma_ends, np.percentile(density, PRINT_ENDS, axis=0) - luma_ends[:, None], luma


def _softplus(z, sharpness):
    return (np.logaddexp(0.0, sharpness * z) / sharpness).astype(np.float32)


def paper_curve(y: np.ndarray) -> np.ndarray:
    """Printing paper response on log10 exposure relative to mid grey (y = log10(lin / 0.18)): straight in
    the middle, a soft shoulder into paper white and a soft toe into paper black (smooth min/max)."""
    shoulder = PAPER_WHITE - _softplus(PAPER_WHITE - y, PAPER_SHOULDER)
    return PAPER_BLACK + _softplus(shoulder - PAPER_BLACK, PAPER_TOE)


def _shoulder(x: np.ndarray, start: float) -> np.ndarray:
    """Identity below ``start``; above it, rolls smoothly towards 1.0 (no hard clip)."""
    room = 1.0 - start
    over = np.maximum(x - start, 0)
    return np.where(x <= start, x, start + room * (1 - np.exp(-over / room)))


def srgb_encode(linear: np.ndarray) -> np.ndarray:
    x = np.clip(linear, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055).astype(np.float32)


def _tone(lin: np.ndarray, shoulder: float, toe: float, paper: bool = False) -> np.ndarray:
    lin = np.maximum(lin, 0)
    if paper:                         # Auto print: already toned; the ends clip like a print's black and white
        return np.minimum(lin, 1.0)
    if toe:
        lin = lin + toe * (1 - lin)
    return _shoulder(lin, shoulder)


LUT_LOW, LUT_STEPS = -6.0, 1024          # log10 exposure range of the preview look-up table
_LUT_CACHE: dict = {}


def _preview_lut(gain: float, shoulder: float, toe: float, paper: bool = False) -> np.ndarray:
    """log exposure (step 1/1024 from -6 to +4) -> sRGB 8-bit, for fast previews."""
    key = (round(gain, 6), shoulder, toe, bool(paper))
    lut = _LUT_CACHE.get(key)
    if lut is None:
        x = LUT_LOW + np.arange(10 * LUT_STEPS + 1, dtype=np.float64) / LUT_STEPS
        lut = np.rint(srgb_encode(_tone(MID_GREY * 10 ** (gain * x), shoulder, toe, paper)) * 255).astype(np.uint8)
        if len(_LUT_CACHE) > 32:
            _LUT_CACHE.clear()
        _LUT_CACHE[key] = lut
    return lut


CHUNK_ROWS = 256                          # rows processed at a time: bounded memory at full resolution
PARALLEL_MIN_PIXELS = 4_000_000


_LIN_CACHE: dict = {}
_ENC_CACHE: dict = {}


def _linear_lut(gain: float) -> np.ndarray:
    """log exposure -> linear light (float32), same grid as the preview LUT."""
    key = round(gain, 6)
    lut = _LIN_CACHE.get(key)
    if lut is None:
        x = LUT_LOW + np.arange(10 * LUT_STEPS + 1, dtype=np.float64) / LUT_STEPS
        lut = (MID_GREY * 10 ** (gain * x)).astype(np.float32)
        _LIN_CACHE.clear() if len(_LIN_CACHE) > 32 else None
        _LIN_CACHE[key] = lut
    return lut


def _encode_lut(shoulder: float, toe: float, paper: bool = False) -> np.ndarray:
    """log10(linear light) from -6 to +2 -> sRGB 8-bit through the tone shoulder."""
    key = (shoulder, toe, bool(paper))
    lut = _ENC_CACHE.get(key)
    if lut is None:
        y = LUT_LOW + np.arange(8 * LUT_STEPS + 1, dtype=np.float64) / LUT_STEPS
        lut = np.rint(srgb_encode(_tone(10 ** y, shoulder, toe, paper)) * 255).astype(np.uint8)
        _ENC_CACHE[key] = lut
    return lut


WHITE_FADE = (1.0, 4.0)        # linear levels where colour fades to neutral (above diffuse white)


def _neutral_above_white(lin: np.ndarray) -> np.ndarray:
    """Fade colour to neutral above white, before the camera matrix.

    Values far above white are not image (opaque film holder, sprocket holes): the matrix's mixing
    would turn their channel differences into strong false colours. Below white nothing changes."""
    luma = lin @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    keep = np.clip((WHITE_FADE[1] - luma) / (WHITE_FADE[1] - WHITE_FADE[0]), 0.0, 1.0)[..., None]
    return luma[..., None] + keep * (lin - luma[..., None])


def _map_rows(log_e: np.ndarray, offsets: np.ndarray, gain: float, saturation: float, shoulder: float, paper: bool,
              toe: float, fast: bool, matrix: np.ndarray | None, out: np.ndarray) -> None:
    """log exposure rows -> output rows: uint8 through look-up tables (previews) or exact float32.

    ``matrix`` (camera profile, linear camera-film RGB -> linear sRGB, neutral-preserving) is applied
    in linear light, before saturation and tone."""
    if fast and matrix is None:
        lut = _preview_lut(gain, shoulder, toe, paper)
        for c in range(3):
            index = (log_e[..., c] + (offsets[c] - LUT_LOW)) * LUT_STEPS
            np.clip(index, 0, len(lut) - 1, out=index)
            out[..., c] = lut[index.astype(np.int32)]
        return
    if fast:
        linear = _linear_lut(gain)
        lin = np.empty(log_e.shape, np.float32)
        for c in range(3):
            index = (log_e[..., c] + (offsets[c] - LUT_LOW)) * LUT_STEPS
            np.clip(index, 0, len(linear) - 1, out=index)
            lin[..., c] = linear[index.astype(np.int32)]
        mixed = _neutral_above_white(lin) @ matrix.T.astype(np.float32)
        np.maximum(mixed, 1e-6, out=mixed)
        np.log10(mixed, out=mixed)
        mixed -= LUT_LOW
        mixed *= LUT_STEPS
        encode = _encode_lut(shoulder, toe, paper)
        np.clip(mixed, 0, len(encode) - 1, out=mixed)
        out[...] = encode[mixed.astype(np.int32)]
        return
    x = (log_e + offsets) * np.float32(gain)
    np.clip(x, -12.0, 12.0, out=x)             # extreme frames (blank, clipped) stay finite
    lin = MID_GREY * np.power(np.float32(10.0), x)
    if matrix is not None:
        lin = np.maximum(_neutral_above_white(lin) @ matrix.T.astype(np.float32), 0)
    if saturation != 1.0:
        luma = lin @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        lin = luma[..., None] + np.float32(saturation) * (lin - luma[..., None])
    encoded = srgb_encode(_tone(lin, shoulder, toe, paper))
    out[...] = encoded if out.dtype == np.float32 else np.rint(encoded * 255.0)


CHROMA_SIGMA = 1.5             # chroma noise blur radius, in pixels of a 1600 px preview (scales with the image)
CHROMA_EDGE = (0.03, 0.09)     # colour steps (log exposure) below / above which detail is smoothed / kept


def chroma_denoise(log_e: np.ndarray, sigma: float) -> np.ndarray:
    """Smooth the colour noise that a hard print grade amplifies, without touching brightness or colour edges.

    Colour = log exposure minus its luma. Its fine detail (below ``sigma``) is removed where the smoothed
    colour is flat and kept where it changes (an edge between two colours), as lab scanners do."""
    luma = log_e @ PRINT_LUMA
    colour = log_e - luma[..., None]
    low = cv2.GaussianBlur(colour, (0, 0), sigmaX=sigma)
    gx = cv2.Sobel(low, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(low, cv2.CV_32F, 0, 1, ksize=3)
    step = np.sqrt((gx * gx + gy * gy).sum(-1)) * np.float32(sigma / 4)      # colour change across the blur radius
    keep = np.clip((step - CHROMA_EDGE[0]) / (CHROMA_EDGE[1] - CHROMA_EDGE[0]), 0.0, 1.0)
    keep = (keep * keep * (3 - 2 * keep))[..., None].astype(np.float32)
    return (luma[..., None] + low + keep * (colour - low)).astype(np.float32)


def render(values: np.ndarray | None, params: FrameParams | None, *, cyan: int = 0, magenta: int = 0,
           yellow: int = 0, density: int = 0, contrast: float = 1.0, saturation: float = 1.0,
           profile: str = "Natural", rotation: int = 0, mirror: bool = False, auto_crop: bool = False,
           show_clipping: bool = False, output_float: bool = False, log_e: np.ndarray | None = None,
           camera_matrix: np.ndarray | None = None, denoise: bool = True) -> np.ndarray:
    """Positive image: uint8 sRGB (preview / JPEG) or float32 sRGB-encoded 0..1 (16-bit TIFF).

    ``log_e`` (from ``scene_log_exposure``) can be passed to skip the inversion (it is not modified).
    Otherwise ``values`` are inverted strip by strip, so a 45 MP frame never needs more than one
    full-size output array.
    """
    tone_contrast, shoulder, toe = PROFILES.get(profile, PROFILES["Natural"])
    gain = contrast * tone_contrast
    # printer lights: + C removes red light (more cyan in the print); + D brightens (as in Classic)
    offsets = np.array([-cyan, -magenta, -yellow], np.float32) * POINT + density * POINT
    fast = not output_float and saturation == 1.0
    paper = bool(params.print_paper) if params is not None else False
    matrix = None if camera_matrix is None or (params is not None and params.mono) else camera_matrix
    source = log_e if log_e is not None else values
    plane = np.empty(source.shape, np.float32 if output_float else np.uint8)

    height, width = source.shape[:2]
    sigma = CHROMA_SIGMA * max(height, width) / 1600 if paper and denoise and not params.mono else 0.0
    pad = int(np.ceil(3 * sigma)) if sigma else 0

    def strip(top):
        first, last = max(0, top - pad), min(height, top + CHUNK_ROWS + pad)     # neighbours for the blur
        rows = slice(first, last)
        chunk = log_e[rows] if log_e is not None else scene_log_exposure(values[rows], params)
        if sigma:
            chunk = chroma_denoise(chunk, sigma)
        chunk = chunk[top - first:top - first + CHUNK_ROWS]
        _map_rows(chunk, offsets, gain, saturation, shoulder, paper, toe, fast, matrix, plane[top:top + CHUNK_ROWS])

    starts = range(0, source.shape[0], CHUNK_ROWS)
    if source.shape[0] * source.shape[1] > PARALLEL_MIN_PIXELS:   # NumPy releases the GIL: strips run in parallel
        with ThreadPoolExecutor(max_workers=min(6, os.cpu_count() or 1)) as pool:
            list(pool.map(strip, starts))
    else:
        for top in starts:
            strip(top)

    if mirror:
        plane = np.fliplr(plane)
    steps = (rotation % 360) // 90
    if steps:
        plane = np.rot90(plane, -steps)
    if auto_crop:
        ch, cw = plane.shape[:2]
        plane = plane[int(ch * 0.05):int(ch * 0.95), int(cw * 0.05):int(cw * 0.95)]
    if output_float:
        return np.ascontiguousarray(plane, dtype=np.float32)
    out = np.ascontiguousarray(plane)
    if show_clipping:
        out[np.all(out >= 250, axis=-1)] = [255, 0, 0]
        out[np.all(out <= 5, axis=-1)] = [0, 0, 255]
    return out


# ----------------------------------------------------------------------------- camera profile
# XYZ (D50) -> linear sRGB (D65), Bradford-adapted (the standard ICC/Lindbloom matrix)
XYZ_D50_TO_SRGB = np.array([[3.1338561, -1.6168667, -0.4906146],
                            [-0.9787684, 1.9161415, 0.0334540],
                            [0.0719453, -0.2289914, 1.4052427]])


@dataclass
class CameraProfile:
    """Camera + light source colour profile measured on an IT8 transparency target.

    ``matrix`` maps linear camera RGB to XYZ D50. It describes the scanning set-up (camera sensor and
    light), not the film: it turns the camera's colours into real colours."""
    name: str
    matrix: np.ndarray
    source: str = ""
    mean_de00: float | None = None

    def working_matrix(self) -> np.ndarray:
        """Linear camera RGB -> linear sRGB, scaled so that equal channels stay neutral (R=G=B -> grey).

        The inversion has already made greys neutral (equal channels); this keeps them neutral and
        only corrects the colours (hue and saturation) for the camera's sensitivities."""
        a = XYZ_D50_TO_SRGB @ np.asarray(self.matrix, np.float64)
        neutral = np.linalg.solve(a, np.ones(3))
        return (a * neutral[None, :]).astype(np.float32)


def load_camera_profile(path: str) -> CameraProfile:
    """Read a profile written by it8_profiler ("Export report" .json)."""
    import json
    from pathlib import Path
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = data.get("camera_rgb_to_xyz_d50_linear_only") or data.get("camera_rgb_to_xyz_d50")
    if raw is None:
        raise ValueError("Not an IT8 profile report (no camera_rgb_to_xyz_d50 matrix).")
    matrix = np.asarray(raw, np.float64)
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)) or abs(np.linalg.det(matrix)) < 1e-9:
        raise ValueError("The profile matrix is invalid.")
    neutral = np.linalg.solve(XYZ_D50_TO_SRGB @ matrix, np.ones(3))
    if np.any(neutral <= 0):
        raise ValueError("The profile has no valid neutral (negative channel).")
    mean_de00 = (data.get("stats_linear_only") or {}).get("mean00") or (data.get("stats") or {}).get("mean00")
    return CameraProfile(name=Path(path).stem, matrix=matrix, source=str(data.get("image", "")),
                         mean_de00=mean_de00)


def neutral_points(values: np.ndarray, params: FrameParams, region: tuple[slice, slice],
                   magenta: int = 0) -> tuple[int, int, int]:
    """Printer-light keys (C, M, Y) that make ``region`` neutral (grey picker), keeping ``magenta``."""
    log_e = scene_log_exposure(values[region], params).reshape(-1, 3)
    mean = np.median(log_e, axis=0)
    diff = mean - mean[1]
    return (int(round(diff[0] / POINT)) + magenta, magenta, int(round(diff[2] / POINT)) + magenta)


def region_log_exposure(values: np.ndarray, params: FrameParams, region: tuple[slice, slice]) -> np.ndarray:
    """Median relative log exposure (per channel) of a region, 0 = mid grey."""
    return np.median(scene_log_exposure(values[region], params).reshape(-1, 3), axis=0)


