# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
"""Colour-accuracy audit harness for SMneg (not part of the app, not collected by pytest).

It runs the *unmodified* SMneg engine (OfficialFilmEngine.load_negative_base + apply_pipeline,
"Natural" profile = the default) on a synthetic colour negative that contains:

  * a 24-step reflective grey wedge (IT8.7/2-like, D = 0.06 .. 2.36, L* ~96 .. ~4),
  * surrounding scene content (balanced / warm / cool / low-key / high-key),
  * an unexposed film rebate (the real film base / orange mask) around the frame.

The negative is produced by a simple film model (per-channel H&D curve with toe and shoulder,
orange mask Dmin, different gammas per layer) and a camera model (light-source colour,
channel crosstalk, ETTR exposure). Output is interpreted as sRGB (the files are untagged,
so this is what every viewer does) and converted to CIE L*a*b* (D65).

For comparison, a ~40-line *prototype* of a base-referenced pipeline is run on the same data
(sample the rebate -> density above base -> per-channel slope from a film profile -> scene-linear ->
sRGB). It exists only to show the numbers a correct approach reaches on the same input.

Usage:
    python tests/audit/audit_color.py                 # uses ./smneg_fixed/src (falls back to ./src)
    python tests/audit/audit_color.py --src src       # audit another copy
    python tests/audit/audit_color.py --nef PATH.NEF  # extra real-negative checks
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

# ------------------------------------------------------------------ colour maths
M_SRGB_TO_XYZ = np.array([[0.4124564, 0.3575761, 0.1804375],
                          [0.2126729, 0.7151522, 0.0721750],
                          [0.0193339, 0.1191920, 0.9503041]])
WHITE_D65 = np.array([0.95047, 1.0, 1.08883])


def srgb_decode(v):
    v = np.clip(v, 0, 1)
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def srgb_encode(v):
    v = np.clip(v, 0, 1)
    return np.where(v <= 0.0031308, v * 12.92, 1.055 * v ** (1 / 2.4) - 0.055)


def srgb_to_lab(rgb):
    xyz = srgb_decode(rgb) @ M_SRGB_TO_XYZ.T / WHITE_D65
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def y_to_L(y):
    y = np.asarray(y, dtype=np.float64)
    return np.where(y > (6 / 29) ** 3, 116 * np.cbrt(y) - 16, y * (29 / 3) ** 3)


def delta_e2000(lab1, lab2):
    """CIEDE2000 (Sharma et al. 2005), vectorised."""
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
    return np.sqrt((dLp / Sl) ** 2 + x ** 2 + y ** 2 + Rt * x * y)


# ------------------------------------------------------------------ synthetic film + camera
GREY_D = 0.06 + 0.10 * np.arange(24)            # reflection densities of the 24 grey steps
GREY_Y = 10 ** -GREY_D
GREY_LAB = np.stack([y_to_L(GREY_Y), np.zeros(24), np.zeros(24)], -1)

STOCKS = {   # orange mask (Dmin) and layer gammas R,G,B; toe / shoulder in log exposure
    "Portra-like": dict(dmin=(0.22, 0.62, 0.92), gamma=(0.55, 0.60, 0.66), toe=-2.4, shoulder=1.6),
    "Ektar-like": dict(dmin=(0.25, 0.68, 0.98), gamma=(0.68, 0.74, 0.82), toe=-2.0, shoulder=1.3),
}
LIGHTS = {   # light colour seen by the camera channels, and camera crosstalk
    "D65": dict(light=(1.00, 1.00, 0.80), xtalk=0.06),
    "LED": dict(light=(1.00, 0.86, 0.52), xtalk=0.12),
}


def film_density(log_h, stock):
    g = np.array(stock["gamma"])
    x = log_h
    toe = np.log10(1 + 10 ** (x - stock["toe"]))            # ~0 below toe, ~(x-toe) above
    sh = np.log10(1 + 10 ** (x - stock["shoulder"]))        # flattens above shoulder
    return np.array(stock["dmin"]) + g * (toe - 0.85 * sh)


def scene(content: str, rng, h=900, w=1350, small_wedge=False):
    """Scene reflectance (linear RGB) with the grey wedge in the middle; rebate mask.
    small_wedge=False: chart-like frame, the wedge dominates the analysis window (like an IT8 shot).
    small_wedge=True : a normal photo with a small wedge in it; scene content spans 0.003..0.95."""
    ny, nx = 9, 14
    lo, hi = (0.02, 0.9) if small_wedge else (0.04, 0.85)   # photo: log-mean reflectance ~13 %
    u = lambda n, a=lo, b=hi: np.exp(rng.uniform(np.log(a), np.log(b), (n, 3)))
    hues = {
        "balanced": lambda n: u(n),
        "warm": lambda n: u(n) * (1.0, 0.55, 0.25),
        "cool": lambda n: u(n) * (0.30, 0.60, 1.0),
        "low-key": lambda n: u(n, lo, 0.12),
        "high-key": lambda n: u(n, 0.25, hi),
    }[content](ny * nx)
    refl = np.repeat(np.repeat(hues.reshape(ny, nx, 3), h // ny + 1, 0), w // nx + 1, 1)[:h, :w].copy()
    # grey wedge: 24 patches, 2 rows of 12, centred (inside SMneg's 20-80 % analysis window)
    ph, pw = (h // 40, w // 60) if small_wedge else (h // 12, w // 20)
    y0, x0 = h // 2 - ph, w // 2 - 6 * pw
    boxes = []
    for i in range(24):
        r, c = divmod(i, 12)
        ys, xs = y0 + r * ph, x0 + c * pw
        refl[ys:ys + ph, xs:xs + pw] = GREY_Y[i]
        m = max(1, ph // 4), max(1, pw // 4)
        boxes.append((ys + m[0], ys + ph - m[0], xs + m[1], xs + pw - m[1]))
    rebate = np.zeros((h, w), bool)
    b = int(0.04 * min(h, w))
    rebate[:b] = rebate[-b:] = True
    rebate[:, :b] = rebate[:, -b:] = True
    return refl, boxes, rebate


def expose(refl, rebate, stock, light, ev=0.0):
    log_h = np.log10(np.clip(refl, 1e-6, None)) + ev * np.log10(2)
    log_h[rebate] = -8.0                                   # unexposed rebate -> film base
    dens = film_density(log_h, stock)
    trans = 10 ** -dens
    x = light["xtalk"]
    M = np.array([[1 - 2 * x, x, x], [x, 1 - 2 * x, x], [x, x, 1 - 2 * x]])
    raw = (trans @ M.T) * np.array(light["light"])
    raw *= 0.85 / raw[rebate].max()                       # ETTR: base at 85 % of full scale
    return raw.astype(np.float32)


# ------------------------------------------------------------------ pipelines
def import_engine(src: Path):
    sys.path.insert(0, str(src.resolve()))
    for name in [m for m in sys.modules if m == "smneg" or m.startswith("smneg.")]:
        del sys.modules[name]
    import smneg.engine as engine
    return engine


def smneg_render(engine, raw, density=0, bits=8, base_override=None):
    """Exactly the app path for a RAW frame with default settings: load_negative_base -> apply_pipeline (Natural)."""
    original = engine.decode_negative
    engine.decode_negative = lambda path, full: raw.copy()
    try:
        if base_override is None:
            base = engine.OfficialFilmEngine.load_negative_base("synthetic", True)
        else:  # same code, but the 'base' is the true rebate value (orange-mask test)
            base = _invert_with_base(engine, raw, base_override)
    finally:
        engine.decode_negative = original
    if bits == 8:
        out = engine.OfficialFilmEngine.apply_pipeline(base, 0, 0, 0, density, 1.0, 1.0, 0, False, False, False)
        return out.astype(np.float64) / 255.0, base
    out = engine.OfficialFilmEngine.apply_pipeline(base, 0, 0, 0, density, 1.0, 1.0, 0, False, False, False,
                                                   output_float=True)
    return np.rint(out * 65535).astype(np.float64) / 65535.0, base


def _invert_with_base(engine, values, base_rgb):
    h, w = values.shape[:2]
    ys, ye, xs, xe = int(h * .2), int(h * .8), int(w * .2), int(w * .8)
    out = np.empty_like(values)
    for c in range(3):
        d = np.clip(values[:, :, c] / base_rgb[c], 1e-4, 1.0)
        d = -np.log10(d)
        lo, hi = np.percentile(d[ys:ye, xs:xe], [0.5, 99.5])
        out[:, :, c] = np.clip((d - lo) / max(hi - lo, 1e-6), 0, 1)
    return out


def prototype_render(raw, rebate, stock, grey_card_box):
    """Base-referenced reference pipeline (audit only): rebate base -> density above base ->
    / layer gamma (film profile) -> scene log exposure -> one global exposure anchor -> sRGB."""
    base = np.median(raw[rebate], axis=0)
    d = -np.log10(np.clip(raw / base, 1e-6, None))          # density above base, per channel
    log_h = d / np.array(stock["gamma"])                    # undo the film's contrast per layer
    ys, ye, xs, xe = grey_card_box                           # one grey-card click (18 % patch)
    anchor = np.median(log_h[ys:ye, xs:xe].reshape(-1, 3), axis=0)  # per channel: neutralises crosstalk
    lin = 10 ** (log_h - anchor) * 0.18
    return srgb_encode(lin)


def patch_lab(img_srgb, boxes):
    return np.array([srgb_to_lab(img_srgb[a:b, c:d].reshape(-1, 3).mean(0)) for a, b, c, d in boxes])


def summarise(lab):
    de = delta_e2000(lab, GREY_LAB)
    chroma = np.hypot(lab[:, 1], lab[:, 2])
    return dict(de_mean=de.mean(), de_max=de.max(), chroma_mean=chroma.mean(), chroma_max=chroma.max(),
                mid_dL=(lab[7:16, 0] - GREY_LAB[7:16, 0]).mean(),
                top9=(lab[:9, 0].min(), lab[:9, 0].max()), bottom5=(lab[-5:, 0].min(), lab[-5:, 0].max()))


def best_density(engine, raw, boxes):
    """Give SMneg its best chance: the single density-key value (-50..50) that minimises mean grey dE."""
    best = None
    for step in range(-50, 51, 2):
        out, _ = smneg_render(engine, raw, density=step)
        s = summarise(patch_lab(out, boxes))
        if best is None or s["de_mean"] < best[1]["de_mean"]:
            best = (step, s)
    return best


# ------------------------------------------------------------------ report
def fmt(s):
    return (f"dE00 mean {s['de_mean']:5.1f} max {s['de_max']:5.1f} | C* mean {s['chroma_mean']:4.1f} "
            f"max {s['chroma_max']:4.1f} | mid-grey dL* {s['mid_dL']:+5.1f} | "
            f"top9 L* {s['top9'][0]:4.1f}-{s['top9'][1]:4.1f} | bottom5 L* {s['bottom5'][0]:4.1f}-{s['bottom5'][1]:4.1f}")


def main():
    ap = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[2]
    default_src = root / "smneg_fixed" / "src" if (root / "smneg_fixed" / "src").is_dir() else root / "src"
    ap.add_argument("--src", type=Path, default=default_src)
    ap.add_argument("--nef", type=Path, default=None)
    args = ap.parse_args()
    engine = import_engine(args.src)
    rng = np.random.default_rng(7)
    print("Note: the prototype sets exposure with ONE grey-card click on GS7, so GS7 is exact by construction;\n"
          "judge it on the other 23 steps (dE mean, C* mean).")
    print(f"SMneg engine from {args.src}\nReference grey L*: " + " ".join(f"{v:.0f}" for v in GREY_LAB[:, 0]))

    # 1. per-patch table, Portra-like / D65 / balanced content / correct exposure
    refl, boxes, rebate = scene("balanced", rng)
    stock, light = STOCKS["Portra-like"], LIGHTS["D65"]
    raw = expose(refl, rebate, stock, light)
    out8, base = smneg_render(engine, raw)
    out16, _ = smneg_render(engine, raw, bits=16)
    lab = patch_lab(out8, boxes)
    proto = prototype_render(raw, rebate, stock, boxes[7])
    plab = patch_lab(proto, boxes)
    print("\n[1] Per-step result, Portra-like, D65, balanced scene, normal exposure")
    print(" step  ref L* | SMneg L*   a*    b*  dE00 | prototype L*   a*    b*  dE00")
    de, pde = delta_e2000(lab, GREY_LAB), delta_e2000(plab, GREY_LAB)
    for i in range(24):
        print(f" GS{i:<3} {GREY_LAB[i,0]:6.1f} | {lab[i,0]:7.1f} {lab[i,1]:5.1f} {lab[i,2]:5.1f} {de[i]:5.1f} |"
              f" {plab[i,0]:11.1f} {plab[i,1]:5.1f} {plab[i,2]:5.1f} {pde[i]:5.1f}")
    print(" SMneg 8-bit  :", fmt(summarise(lab)))
    print(" SMneg 16-bit :", fmt(summarise(patch_lab(out16, boxes))))
    step, sbest = best_density(engine, raw, boxes)
    print(f" SMneg best density key ({step:+d}):", fmt(sbest))
    print(" prototype    :", fmt(summarise(plab)))

    # 2. matrix of stocks x lights (like the Reddit table)
    print("\n[2] Grey dE00 mean (balanced scene, normal exposure)")
    print(f" {'roll':<24}{'SMneg':>8}{'SMneg best D':>14}{'prototype':>11}")
    for sname, st in STOCKS.items():
        for lname, li in LIGHTS.items():
            r = expose(refl, rebate, st, li)
            s0 = summarise(patch_lab(smneg_render(engine, r)[0], boxes))
            _, sb = best_density(engine, r, boxes)
            sp = summarise(patch_lab(prototype_render(r, rebate, st, boxes[7]), boxes))
            print(f" {sname + ', ' + lname:<24}{s0['de_mean']:8.1f}{sb['de_mean']:14.1f}{sp['de_mean']:11.1f}")

    # 3. claim 1a: drift with film exposure (same scene, EV -2..+2), normal photo with a small wedge
    refl, boxes, rebate = scene("balanced", np.random.default_rng(3), small_wedge=True)
    print("\n[3] Normal photo with a small wedge, film exposure changed (Portra-like, D65): grey patch GS7 (L* ref "
          f"{GREY_LAB[7,0]:.1f}) and wedge mean chroma")
    for ev in (-2, -1, 0, 1, 2):
        r = expose(refl, rebate, stock, light, ev)
        l = patch_lab(smneg_render(engine, r)[0], boxes)
        pl = patch_lab(prototype_render(r, rebate, stock, boxes[7]), boxes)
        print(f"  EV {ev:+d}: SMneg GS7 L*a*b* = {l[7,0]:5.1f} {l[7,1]:+5.1f} {l[7,2]:+5.1f}, wedge C* mean "
              f"{np.hypot(l[:,1], l[:,2]).mean():4.1f} | prototype wedge dE mean {summarise(pl)['de_mean']:4.1f} C* mean "
              f"{summarise(pl)['chroma_mean']:4.1f}")

    # 4. claim 1b: drift with scene content (identical grey wedge, identical film/camera)
    print("\n[4] Normal photo, identical small grey wedge, different surrounding content (Portra-like, D65, EV 0)")
    for content in ("balanced", "warm", "cool", "low-key", "high-key"):
        rf, bx, rb = scene(content, np.random.default_rng(11), small_wedge=True)
        r = expose(rf, rb, stock, light)
        l = patch_lab(smneg_render(engine, r)[0], bx)
        pl = patch_lab(prototype_render(r, rb, stock, bx[7]), bx)
        s = summarise(l)
        print(f"  {content:<9}: SMneg GS7 = {l[7,0]:5.1f} {l[7,1]:+5.1f} {l[7,2]:+5.1f}  dE mean {s['de_mean']:5.1f} "
              f"C* mean {s['chroma_mean']:4.1f} | prototype dE mean {summarise(pl)['de_mean']:4.1f} C* mean "
              f"{summarise(pl)['chroma_mean']:4.1f}")

    # 5. claim 1c: the orange mask / base value has no effect
    refl, boxes, rebate = scene("balanced", rng)
    raw = expose(refl, rebate, stock, light)
    _, base = smneg_render(engine, raw)
    print("\n[5] Does the film base matter? (max abs difference of load_negative_base output, 0..1 scale)")
    true_base = np.median(raw[rebate], axis=0)
    b_true = _invert_with_base(engine, raw, true_base)
    print(f"  99.5-percentile 'base' {base_rgb_str(engine, raw)} vs real rebate base {np.round(true_base, 4)}")
    print(f"  output difference, percentile base vs real rebate base : {np.abs(b_true - base).max():.2e}")
    scaled = raw * np.array([0.5, 1.7, 3.0], dtype=np.float32)          # pre-scale channels (= other mask / light)
    _, b_scaled = smneg_render(engine, scaled)
    print(f"  output difference, channels pre-scaled by (0.5,1.7,3.0)  : {np.abs(b_scaled - base).max():.2e}")
    _, b_half = smneg_render(engine, raw * np.float32(0.5))
    print(f"  output difference, camera exposure -1 EV                 : {np.abs(b_half - base).max():.2e}")

    # 6. claim 2: what the 'Natural' curve is
    x = np.linspace(0, 1, 6)
    print("\n[6] Default tone: display value = stretched_density ** (1/1.4)")
    for v in x:
        print(f"  stretched density {v:.1f} -> code {v ** (1/1.4):.3f} -> L* {srgb_to_lab(np.full(3, v ** (1/1.4)))[0]:5.1f}")

    scientific_comparison(engine, args.src)

    if args.nef:
        real_negative_checks(engine, args.nef)


def scientific_comparison(engine, src: Path):
    """[8] Classic vs Scientific engine on a whole synthetic roll (15 photos + 1 chart frame)."""
    try:
        from smneg import scientific as sc
    except ImportError:
        print("\n[8] (no scientific engine in this copy)")
        return
    print("\n[8] Classic vs Scientific on a roll: 15 photos (5 scene types x EV -1/0/+1) + 1 chart frame")
    print(f" {'roll':<20}{'chart dE auto':>22}{'chart dE best D':>22}{'photos grey C* mean/max':>30}")
    for sname, st in STOCKS.items():
        for lname, li in LIGHTS.items():
            photos = []
            for content in ("balanced", "warm", "cool", "low-key", "high-key"):
                for ev in (-1, 0, 1):
                    rf, bx, rb = scene(content, np.random.default_rng(11), small_wedge=True)
                    photos.append((expose(rf, rb, st, li, ev), bx))
            rf, cbx, rb = scene("balanced", np.random.default_rng(7))
            chart = expose(rf, rb, st, li)
            stats = [sc.frame_stats(r) for r, _ in photos] + [sc.frame_stats(chart)]
            roll = sc.roll_model(stats)
            cp = sc.frame_params(stats[-1], roll)
            sci = lambda d=0: patch_lab(sc.render(chart, cp, density=d, output_float=True).astype(np.float64), cbx)
            sci_auto = delta_e2000(sci(), GREY_LAB).mean()
            sci_best = min(delta_e2000(sci(d), GREY_LAB).mean() for d in range(-20, 21, 2))
            cla_auto = summarise(patch_lab(smneg_render(engine, chart)[0], cbx))["de_mean"]
            cla_best = best_density(engine, chart, cbx)[1]["de_mean"]
            sc_c = [np.hypot(*patch_lab(sc.render(r, sc.frame_params(s, roll), output_float=True)
                                        .astype(np.float64), bx)[:, 1:].T).mean() for (r, bx), s in zip(photos, stats)]
            cl_c = [summarise(patch_lab(smneg_render(engine, r)[0], bx))["chroma_mean"] for r, bx in photos]
            print(f" {sname + ', ' + lname:<20}{cla_auto:>10.1f} -> {sci_auto:<9.1f}{cla_best:>10.1f} -> {sci_best:<9.1f}"
                  f"{np.mean(cl_c):>9.1f}/{np.max(cl_c):<4.1f} -> {np.mean(sc_c):.1f}/{np.max(sc_c):.1f}")
    print(" (Classic -> Scientific. 'best D' = after the single density setting that fits best.)")


def base_rgb_str(engine, raw):
    h, w = raw.shape[:2]
    inner = raw[int(h * .2):int(h * .8), int(w * .2):int(w * .8)]
    return str(np.round([np.percentile(inner[:, :, c], 99.5) for c in range(3)], 4))


def real_negative_checks(engine, nef: Path):
    print(f"\n[7] Real negative: {nef.name}")
    vals = engine.decode_negative(str(nef), False)
    print(f"  decoded {vals.shape} {vals.dtype}, range {vals.min():.4f}..{vals.max():.4f}, "
          f"channel medians {np.round(np.median(vals.reshape(-1, 3), 0), 4)}")
    full, _ = smneg_render(engine, vals)
    h, w = vals.shape[:2]
    crop = vals[:, : int(w * 0.6)].copy()        # same negative, different framing (content)
    part, _ = smneg_render(engine, crop)
    region = (slice(int(h * .4), int(h * .6)), slice(int(w * .3), int(w * .5)))
    a = srgb_to_lab(full[region].reshape(-1, 3).mean(0))
    b = srgb_to_lab(part[region].reshape(-1, 3).mean(0))
    print(f"  same pixels, full frame   L*a*b* = {np.round(a, 1)}")
    print(f"  same pixels, 60 % crop    L*a*b* = {np.round(b, 1)}  -> dE00 {delta_e2000(a, b):.1f}")
    half, _ = smneg_render(engine, vals * np.float32(0.5))
    print(f"  scan exposure -1 EV: max code difference {np.abs(half - full).max() * 255:.1f}/255")


if __name__ == "__main__":
    main()
