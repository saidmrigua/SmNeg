# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
"""Film profile: calibration of a film + scanning set-up from a colour chart photographed on the film.

A ColorChecker shot in daylight on a roll, scanned on the usual rig, gives three things the automatic
engine can only estimate:

* a **dye crosstalk matrix** in density. The cyan, magenta and yellow dyes (and the camera's overlapping
  filters) each leak into the other channels; that leak is linear in density, so it is undone by a 3x3
  matrix on ``log10`` of the scan, *before* the film base and the inversion. Rows sum to 1, so a grey
  stays grey (the matrix only moves colour differences);
* the **dye-layer slopes** (neutral balance), measured on the chart's six greys instead of guessed
  from the picture;
* the **film contrast** (gamma, in green-equivalent density per decade of exposure).

The fit compares the rendered patches with the chart's published colours (CIEDE2000, lightness at half
weight because exposure and tone are set separately). This is the same physics as the density-domain
crosstalk correction used by lab scanners; the code is SMneg's own.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

# ----------------------------------------------------------------------------- chart reference
# X-Rite ColorChecker Classic 24, published CIELAB D50 (2°), formulation since November 2014.
# Row-major as printed: row 1 = dark skin ... cyan, row 4 = white ... black.
COLORCHECKER_24_NAMES = (
    "Dark skin", "Light skin", "Blue sky", "Foliage", "Blue flower", "Bluish green",
    "Orange", "Purplish blue", "Moderate red", "Purple", "Yellow green", "Orange yellow",
    "Blue", "Green", "Red", "Yellow", "Magenta", "Cyan",
    "White 9.5", "Neutral 8", "Neutral 6.5", "Neutral 5", "Neutral 3.5", "Black 2",
)
COLORCHECKER_24_LAB_D50 = np.array([
    [37.54, 14.37, 14.92], [64.66, 19.27, 17.50], [49.32, -3.82, -22.54], [43.46, -12.74, 22.72],
    [54.94, 9.61, -24.79], [70.48, -32.26, -0.37], [62.73, 35.83, 56.50], [39.43, 10.75, -45.17],
    [50.57, 48.64, 16.67], [30.10, 22.54, -20.87], [71.77, -24.13, 58.19], [71.51, 18.24, 67.37],
    [28.37, 15.42, -49.80], [54.38, -39.72, 32.27], [42.43, 51.05, 28.62], [81.80, 2.67, 80.41],
    [50.63, 51.28, -14.12], [49.57, -29.71, -28.32], [95.19, -1.03, 2.93], [81.29, -0.57, 0.44],
    [66.89, -0.75, -0.06], [50.76, -0.13, 0.14], [35.63, -0.46, -0.48], [20.64, 0.07, -0.46],
])
ROWS, COLS = 4, 6
GREYS = np.arange(18, 24)            # white .. black
TONE_GREYS = np.arange(18, 23)       # white .. 3.5: the straight part used for gamma (black sits in the toe)

# ----------------------------------------------------------------------------- colour maths
_D50 = np.array([0.96422, 1.0, 0.82521])
_D65 = np.array([0.95047, 1.0, 1.08883])
_BRADFORD = np.array([[0.8951, 0.2664, -0.1614], [-0.7502, 1.7135, 0.0367], [0.0389, -0.0685, 1.0296]])
_SRGB_TO_XYZ_D65 = np.array([[0.4124564, 0.3575761, 0.1804375],
                             [0.2126729, 0.7151522, 0.0721750],
                             [0.0193339, 0.1191920, 0.9503041]])


def _adapt(src_white, dst_white):
    cone_src, cone_dst = _BRADFORD @ src_white, _BRADFORD @ dst_white
    return np.linalg.inv(_BRADFORD) @ np.diag(cone_dst / cone_src) @ _BRADFORD


_D50_TO_D65 = _adapt(_D50, _D65)


def _f(t):
    return np.where(t > (6 / 29) ** 3, np.cbrt(t), t / (3 * (6 / 29) ** 2) + 4 / 29)


def _finv(f):
    return np.where(f > 6 / 29, f ** 3, 3 * (6 / 29) ** 2 * (f - 4 / 29))


def lab_to_xyz(lab, white):
    L, a, b = np.moveaxis(np.asarray(lab, float), -1, 0)
    fy = (L + 16) / 116
    return np.stack([_finv(fy + a / 500), _finv(fy), _finv(fy - b / 200)], -1) * white


def xyz_to_lab(xyz, white):
    f = _f(np.asarray(xyz, float) / white)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def linear_srgb_to_lab(rgb):
    """Linear sRGB (D65) -> CIELAB D65."""
    return xyz_to_lab(np.asarray(rgb, float) @ _SRGB_TO_XYZ_D65.T, _D65)


def reference_lab_d65(lab_d50=COLORCHECKER_24_LAB_D50):
    """Chart values (D50) adapted to the D65 of sRGB output, Bradford."""
    return xyz_to_lab(lab_to_xyz(lab_d50, _D50) @ _D50_TO_D65.T, _D65)


def delta_e2000(lab1, lab2, k_l=1.0):
    L1, a1, b1 = np.moveaxis(np.asarray(lab1, float), -1, 0)
    L2, a2, b2 = np.moveaxis(np.asarray(lab2, float), -1, 0)
    C1, C2 = np.hypot(a1, b1), np.hypot(a2, b2)
    Cb7 = ((C1 + C2) / 2) ** 7
    G = 0.5 * (1 - np.sqrt(Cb7 / (Cb7 + 25 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p, h2p = np.degrees(np.arctan2(b1, a1p)) % 360, np.degrees(np.arctan2(b2, a2p)) % 360
    prod = C1p * C2p
    dh = h2p - h1p
    dh = np.where(prod == 0, 0, np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh)))
    dLp, dCp = L2 - L1, C2p - C1p
    dHp = 2 * np.sqrt(prod) * np.sin(np.radians(dh / 2))
    Lbp, Cbp = (L1 + L2) / 2, (C1p + C2p) / 2
    hs = h1p + h2p
    hbp = np.where(prod == 0, hs, np.where(np.abs(h1p - h2p) <= 180, hs / 2,
                                           np.where(hs < 360, (hs + 360) / 2, (hs - 360) / 2)))
    T = (1 - 0.17 * np.cos(np.radians(hbp - 30)) + 0.24 * np.cos(np.radians(2 * hbp))
         + 0.32 * np.cos(np.radians(3 * hbp + 6)) - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    dth = 30 * np.exp(-(((hbp - 275) / 25) ** 2))
    Rc = 2 * np.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7))
    Sl = 1 + 0.015 * (Lbp - 50) ** 2 / np.sqrt(20 + (Lbp - 50) ** 2)
    Sc, Sh = 1 + 0.045 * Cbp, 1 + 0.015 * Cbp * T
    Rt = -np.sin(np.radians(2 * dth)) * Rc
    x, y = dCp / Sc, dHp / Sh
    return np.sqrt((dLp / (k_l * Sl)) ** 2 + x ** 2 + y ** 2 + Rt * x * y)


# ----------------------------------------------------------------------------- the profile
@dataclass
class FilmProfile:
    name: str
    matrix: list                     # 3x3 density crosstalk unmix, rows sum to 1
    slopes: list                     # dye-layer slope ratios (green = 1)
    gamma: float                     # film contrast, green-equivalent density per decade of exposure
    chart: str = "ColorChecker 24"
    delta_e_before: float | None = None   # mean CIEDE2000 of the chart without the crosstalk matrix
    delta_e_after: float | None = None    # ... with it
    grey_chroma_after: float | None = None
    source: str = ""
    created: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    kind: str = "smneg-film-profile"

    @property
    def matrix_array(self) -> np.ndarray:
        return np.asarray(self.matrix, np.float32)

    @property
    def slopes_array(self) -> np.ndarray:
        return np.asarray(self.slopes, np.float32)

    def save(self, path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        return path


def load_film_profile(path) -> FilmProfile:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("kind") != "smneg-film-profile":
        raise ValueError("Not an SMneg film profile.")
    matrix = np.asarray(data.get("matrix"), float)
    slopes = np.asarray(data.get("slopes"), float)
    gamma = float(data.get("gamma", 0))
    if matrix.shape != (3, 3) or slopes.shape != (3,) or not np.all(np.isfinite(matrix)) \
            or not np.all(np.isfinite(slopes)) or not np.all(slopes > 0) or not 0.1 < gamma < 3:
        raise ValueError("The film profile values are invalid.")
    if not np.allclose(matrix.sum(1), 1, atol=1e-3) or abs(np.linalg.det(matrix)) < 1e-3:
        raise ValueError("The crosstalk matrix must be invertible with rows summing to 1.")
    known = {f for f in FilmProfile.__dataclass_fields__}
    return FilmProfile(**{k: v for k, v in data.items() if k in known})


def unmix(values: np.ndarray, matrix: np.ndarray, chunk_rows: int = 256) -> np.ndarray:
    """Apply the density crosstalk matrix to a linear scan: log10(v') = M · log10(v)."""
    v = np.asarray(values, np.float32)
    out = np.empty_like(v)
    m = np.asarray(matrix, np.float32).T
    for top in range(0, v.shape[0], chunk_rows):
        rows = np.log10(np.clip(v[top:top + chunk_rows], 1e-6, None))
        out[top:top + chunk_rows] = np.power(np.float32(10.0), rows @ m)
    return out


# ----------------------------------------------------------------------------- chart geometry
_CORNER_PATCHES = (0, COLS - 1, ROWS * COLS - 1, (ROWS - 1) * COLS)   # dark skin, bluish green, black, white


def _order_quad(points):
    """Four points -> cyclic order around their centre (any start)."""
    p = np.asarray(points, float)
    centre = p.mean(0)
    angle = np.arctan2(p[:, 1] - centre[1], p[:, 0] - centre[0])
    return p[np.argsort(angle)]


def candidate_layouts(points):
    """The 8 ways (4 rotations x mirror) the clicked corner patches can map onto the chart.
    Each layout gives the 24 patch centres (x, y), row-major in chart order."""
    quad = _order_quad(points)
    layouts = []
    for mirror in (False, True):
        q = quad[::-1] if mirror else quad
        for shift in range(4):
            c = np.roll(q, -shift, axis=0)        # c[0]=patch 1, c[1]=patch 6, c[2]=patch 24, c[3]=patch 19
            centres = []
            for r in range(ROWS):
                v = r / (ROWS - 1)
                for k in range(COLS):
                    u = k / (COLS - 1)
                    top = c[0] + (c[1] - c[0]) * u
                    bottom = c[3] + (c[2] - c[3]) * u
                    centres.append(top + (bottom - top) * v)
            layouts.append(np.array(centres))
    return layouts


def sample_patches(values, centres, radius):
    """Median linear RGB of a square around each patch centre."""
    h, w = values.shape[:2]
    out = []
    for x, y in centres:
        x, y, r = int(round(x)), int(round(y)), max(1, int(radius))
        block = values[max(0, y - r):min(h, y + r + 1), max(0, x - r):min(w, x + r + 1)].reshape(-1, 3)
        out.append(np.median(block, axis=0))
    return np.asarray(out, float)


# ----------------------------------------------------------------------------- the fit
def _matrix(p):
    """6 off-diagonal terms -> 3x3 with rows summing to 1."""
    m = np.zeros((3, 3))
    m[0, 1], m[0, 2], m[1, 0], m[1, 2], m[2, 0], m[2, 1] = p
    m[np.diag_indices(3)] = 1 - m.sum(1)
    return m


def predict(patches, base, matrix):
    """Rendered chart (linear sRGB) for a crosstalk matrix, with slopes and contrast solved on the greys.
    Returns (rgb, slopes, gamma)."""
    density = (np.log10(base) - np.log10(np.clip(patches, 1e-6, None))) @ np.asarray(matrix).T
    g = density[TONE_GREYS]
    slopes = np.array([np.dot(g[:, 1], g[:, c]) / max(np.dot(g[:, c], g[:, c]), 1e-12) for c in range(3)])
    level = density * slopes                                  # green-equivalent density
    target = np.log10(lab_to_xyz(COLORCHECKER_24_LAB_D50[TONE_GREYS], _D50)[:, 1])
    gamma, offset = np.polyfit(target, level[TONE_GREYS].mean(1), 1)   # density = gamma·log10(Y) + offset
    gamma = max(gamma, 0.05)
    rgb = 10 ** ((level - offset) / gamma)
    return rgb, slopes, gamma


def fit_film_profile(patches, base, name="Film profile", ridge=0.05, iterations=60):
    """Fit the crosstalk matrix to a chart photographed on film. ``patches`` (24x3) and ``base`` (3,)
    are linear scan values in the same units (before any unmix)."""
    patches = np.asarray(patches, float)
    base = np.asarray(base, float)
    reference = reference_lab_d65()

    def residuals(p):
        rgb, _, _ = predict(patches, base, _matrix(p))
        de = delta_e2000(linear_srgb_to_lab(np.clip(rgb, 1e-6, None)), reference, k_l=2.0)
        return np.concatenate([de, ridge * 100 * np.asarray(p)])

    p = np.zeros(6)
    lam = 1e-2
    cost = float(np.sum(residuals(p) ** 2))
    for _ in range(iterations):                                # Levenberg-Marquardt, numeric Jacobian
        r = residuals(p)
        jac = np.empty((len(r), 6))
        for i in range(6):
            step = np.zeros(6)
            step[i] = 1e-4
            jac[:, i] = (residuals(p + step) - r) / 1e-4
        while True:
            a = jac.T @ jac + lam * np.diag(np.diag(jac.T @ jac) + 1e-9)
            candidate = np.clip(p - np.linalg.solve(a, jac.T @ r), -0.6, 0.6)
            new_cost = float(np.sum(residuals(candidate) ** 2))
            if new_cost < cost:
                p, cost, lam = candidate, new_cost, max(lam / 3, 1e-7)
                break
            lam *= 4
            if lam > 1e6:
                break
        if lam > 1e6 or np.linalg.norm(jac.T @ r) < 1e-6:
            break

    def report(matrix):
        rgb, slopes, gamma = predict(patches, base, matrix)
        lab = linear_srgb_to_lab(np.clip(rgb, 1e-6, None))
        colour_de = delta_e2000(lab, reference, k_l=2.0)
        return lab, colour_de, slopes, gamma

    _, before, _, _ = report(np.eye(3))
    lab, after, slopes, gamma = report(_matrix(p))
    grey_chroma = float(np.hypot(lab[GREYS, 1], lab[GREYS, 2]).mean())
    return FilmProfile(
        name=name, matrix=np.round(_matrix(p), 6).tolist(), slopes=np.round(slopes / slopes[1], 6).tolist(),
        gamma=round(float(gamma), 6), delta_e_before=round(float(before.mean()), 3),
        delta_e_after=round(float(after.mean()), 3), grey_chroma_after=round(grey_chroma, 3),
    )


def best_layout(values, points, base, radius):
    """Pick the chart orientation that the clicked corners describe (the one whose fit is best)."""
    best = None
    for centres in candidate_layouts(points):
        patches = sample_patches(values, centres, radius)
        rgb, _, _ = predict(patches, base, np.eye(3))
        lab = linear_srgb_to_lab(np.clip(rgb, 1e-6, None))
        score = float(delta_e2000(lab, reference_lab_d65(), k_l=2.0).mean())
        if best is None or score < best[0]:
            best = (score, centres, patches)
    return best[1], best[2]
