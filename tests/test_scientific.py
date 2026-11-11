# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
"""Accuracy tests of the scientific engine on a synthetic colour negative (film + camera model from
tests/audit/audit_color.py). Thresholds are measured values with a margin, so a regression fails."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent / "audit"))
from audit_color import (  # noqa: E402
    GREY_LAB, LIGHTS, STOCKS, delta_e2000, expose, patch_lab, scene, srgb_to_lab,
)

from smneg import scientific as sc  # noqa: E402

H, W = 360, 540


def roll(stock="Portra-like", light="D65"):
    st, li = STOCKS[stock], LIGHTS[light]
    photos = []
    for content in ("balanced", "warm", "cool", "low-key", "high-key"):
        for ev in (-1, 0, 1):
            refl, boxes, rebate = scene(content, np.random.default_rng(11), H, W, small_wedge=True)
            photos.append((expose(refl, rebate, st, li, ev), boxes))
    refl, chart_boxes, rebate = scene("balanced", np.random.default_rng(7), H, W)
    chart = expose(refl, rebate, st, li, 0)
    stats = [sc.frame_stats(r) for r, _ in photos] + [sc.frame_stats(chart)]
    return photos, (chart, chart_boxes), stats, sc.roll_model(stats)


def grey_lab(values, params, boxes, **keys):
    return patch_lab(sc.render(values, params, output_float=True, **keys).astype(np.float64), boxes)


@pytest.fixture(scope="module")
def portra():
    return roll()


def test_rebate_is_found_and_used(portra):
    photos, _, stats, model = portra
    assert all(s.source == "rebate" for s in stats)
    raw, _ = photos[0]
    _, _, rebate = scene("balanced", np.random.default_rng(11), H, W, small_wedge=True)
    true_base = np.median(raw[rebate], axis=0)
    assert np.abs(np.log10(stats[0].base) - np.log10(true_base)).max() < 0.01


def test_grey_scale_is_neutral_whatever_the_scene(portra):
    photos, _, stats, model = portra
    chroma = []
    for (raw, boxes), s in zip(photos, stats):
        lab = grey_lab(raw, sc.frame_params(s, model), boxes)
        chroma.append(np.hypot(lab[:, 1], lab[:, 2]).mean())
    assert np.mean(chroma) < 3.0          # measured 2.3 (Classic: up to 10 on these scenes)
    assert np.max(chroma) < 3.5


def test_tone_reproduction_of_a_chart(portra):
    _, (chart, boxes), stats, model = portra
    params = sc.frame_params(stats[-1], model)
    auto = delta_e2000(grey_lab(chart, params, boxes), GREY_LAB).mean()
    best = min(delta_e2000(grey_lab(chart, params, boxes, density=d), GREY_LAB).mean() for d in range(-20, 21, 2))
    assert auto < 6.0                     # measured ~4 (Classic default: 16)
    assert best < 3.6                     # measured ~3.2 (Classic with its best density key: 6.0)


def test_scan_exposure_does_not_change_the_result(portra):
    photos, _, _, _ = portra
    raw, boxes = photos[1]
    a = sc.render(raw, sc.frame_params(*_alone(raw)))
    b = sc.render(raw * np.float32(0.5), sc.frame_params(*_alone(raw * np.float32(0.5))))
    assert np.abs(a.astype(int) - b.astype(int)).max() <= 1


def _alone(raw):
    stats = sc.frame_stats(raw)
    return stats, sc.roll_model([stats])


def test_bare_light_is_not_taken_for_the_base():
    st, li = STOCKS["Portra-like"], LIGHTS["D65"]
    refl, boxes, rebate = scene("balanced", np.random.default_rng(3), H, W, small_wedge=True)
    raw = expose(refl, rebate, st, li)
    true_base = np.median(raw[rebate], axis=0)
    light = np.array(li["light"], np.float32) * raw[rebate].max() / 0.85 * 0.97
    raw[:, -20:] = light                      # a strip of bare light beside the film
    base, source = sc.estimate_base(raw)
    assert source == "rebate"
    assert np.abs(np.log10(base) - np.log10(true_base)).max() < 0.01


def test_black_and_white_negative_is_neutral():
    rng = np.random.default_rng(4)
    density = rng.uniform(0.1, 1.6, (H, W)).astype(np.float32)
    density[:20] = density[-20:] = 0.0        # rebate
    light = np.array([0.8, 0.9, 0.7], np.float32)
    raw = (10 ** -(density + 0.25))[..., None] * light
    stats = sc.frame_stats(raw)
    assert stats.mono
    out = sc.render(raw, sc.frame_params(stats, sc.roll_model([stats])), output_float=True)
    lab = srgb_to_lab(out.reshape(-1, 3).astype(np.float64))
    assert np.hypot(lab[:, 1], lab[:, 2]).max() < 0.5


def test_preview_lookup_table_matches_exact_rendering(portra):
    photos, _, stats, model = portra
    raw, _ = photos[0]
    params = sc.frame_params(stats[0], model)
    keys = dict(cyan=3, magenta=-2, yellow=1, density=-4, contrast=1.1, profile="S Curve")
    fast = sc.render(raw, params, **keys)
    exact = np.rint(sc.render(raw, params, output_float=True, **keys) * 255)
    assert np.abs(fast.astype(int) - exact.astype(int)).max() <= 1


def test_printer_lights_move_the_right_channel(portra):
    photos, _, stats, model = portra
    raw, boxes = photos[0]
    params = sc.frame_params(stats[0], model)
    base = grey_lab(raw, params, boxes)
    cyan = grey_lab(raw, params, boxes, cyan=4)          # more cyan: a* goes down (less red)
    yellow = grey_lab(raw, params, boxes, yellow=4)      # more yellow: b* goes up
    brighter = grey_lab(raw, params, boxes, density=4)
    assert (cyan[8:16, 1] < base[8:16, 1]).all()
    assert (yellow[8:16, 2] > base[8:16, 2]).all()
    assert (brighter[8:16, 0] > base[8:16, 0]).all()


def test_neutral_picker_makes_a_patch_grey(portra):
    photos, _, stats, model = portra
    raw, boxes = photos[2]                               # "cool" scene
    params = sc.frame_params(stats[2], model)
    a, b, c, d = boxes[9]
    cyan, magenta, yellow = sc.neutral_points(raw, params, (slice(a, b), slice(c, d)))
    lab = grey_lab(raw, params, boxes, cyan=cyan, magenta=magenta, yellow=yellow)
    assert np.hypot(lab[9, 1], lab[9, 2]) < 1.0


def test_preview_and_full_resolution_agree(portra):
    import cv2
    photos, _, stats, model = portra
    raw, _ = photos[0]
    params = sc.frame_params(stats[0], model)            # statistics come from the preview
    full = cv2.resize(raw, (W * 3, H * 3), interpolation=cv2.INTER_LINEAR)
    small = sc.render(raw, params, output_float=True)
    big = cv2.resize(sc.render(full, params, output_float=True), (W, H), interpolation=cv2.INTER_AREA)
    de = delta_e2000(srgb_to_lab(small.astype(np.float64)), srgb_to_lab(big.astype(np.float64)))
    assert np.median(de) < 0.5


# ---------------------------------------------------------------- camera profile (IT8 transparency target)
Z8_MATRIX = [[2.1499, 0.3287, 0.0878], [0.8695, 1.366, -0.3325], [0.0333, -0.2382, 1.874]]   # measured on a Z8


def _profile_file(tmp_path, matrix=Z8_MATRIX):
    import json
    path = tmp_path / "camera.json"
    path.write_text(json.dumps({"camera_rgb_to_xyz_d50": matrix, "stats": {"mean00": 1.04}, "image": "it8.nef"}))
    return path


def test_camera_profile_loads_and_keeps_neutrals(tmp_path):
    profile = sc.load_camera_profile(str(_profile_file(tmp_path)))
    assert profile.mean_de00 == 1.04
    a = profile.working_matrix()
    np.testing.assert_allclose(a @ np.ones(3), np.ones(3), atol=1e-5)
    grey = np.repeat(np.linspace(-2.0, 0.6, 50, dtype=np.float32)[:, None], 3, axis=1)[None]   # equal channels
    for fast in (True, False):
        out = sc.render(None, None, log_e=grey, camera_matrix=a, output_float=not fast)
        lab = srgb_to_lab(out.reshape(-1, 3).astype(np.float64) / (1 if not fast else 255))
        assert np.hypot(lab[:, 1], lab[:, 2]).max() < 0.6


def test_camera_profile_changes_colours_not_greys(portra, tmp_path):
    photos, _, stats, model = portra
    raw, boxes = photos[0]
    params = sc.frame_params(stats[0], model)
    a = sc.load_camera_profile(str(_profile_file(tmp_path))).working_matrix()
    plain = sc.render(raw, params, output_float=True)
    profiled = sc.render(raw, params, output_float=True, camera_matrix=a)
    assert np.abs(plain - profiled).mean() > 0.005                       # colours do change
    g0 = patch_lab(plain.astype(np.float64), boxes)
    g1 = patch_lab(profiled.astype(np.float64), boxes)
    assert np.abs(g1[:, 0] - g0[:, 0]).max() < 1.5                       # grey lightness kept


def test_film_holder_stays_neutral_with_a_profile(tmp_path):
    a = sc.load_camera_profile(str(_profile_file(tmp_path))).working_matrix()
    holder = np.array([[[3.0, 2.2, 1.6]]], np.float32)                   # far above white, unequal channels
    out = sc.render(None, None, log_e=holder, camera_matrix=a)
    assert np.ptp(out.astype(int)) <= 3


def test_invalid_profiles_are_rejected(tmp_path):
    import json
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"something": 1}))
    with pytest.raises(ValueError):
        sc.load_camera_profile(str(bad))
    with pytest.raises(ValueError):
        sc.load_camera_profile(str(_profile_file(tmp_path, [[1, 0, 0], [0, 0, 0], [0, 0, 1]])))


def test_a_colourless_colour_negative_is_not_taken_for_black_and_white():
    st, li = STOCKS["Portra-like"], LIGHTS["D65"]
    refl = np.full((H, W, 3), 0.25)                       # overcast sky: almost no colour
    refl[: H // 2] = (0.30, 0.32, 0.36)
    rebate = np.zeros((H, W), bool)
    rebate[:15] = rebate[-15:] = True
    stats = sc.frame_stats(expose(refl, rebate, st, li))
    assert not stats.mono


def test_auto_print_fills_the_paper_and_keeps_greys_neutral(portra):
    photos, _, stats, model = portra
    for (raw, boxes), s in list(zip(photos, stats))[::3]:
        printed = sc.frame_params(s, model, auto_print=True, meter=sc.METER_STRENGTHS["balanced"])
        assert printed.print_paper and printed.bounds is not None
        out = sc.render(raw, printed, output_float=True).astype(np.float64)
        lab = srgb_to_lab(out[::4, ::4].reshape(-1, 3))
        low, high = np.percentile(lab[:, 0], [1, 99.7])
        assert low < 15 and high > 55            # black to white; a low-key frame stays a little darker
        wedge = patch_lab(out, boxes)
        assert np.hypot(wedge[:, 1], wedge[:, 2]).mean() < 2.0          # measured 0.5 (Classic: 2.7)
        assert np.all(np.diff(wedge[:, 0]) < 0.5)                       # the grey scale stays in order


def test_paper_curve_is_monotonic_and_bounded():
    y = np.linspace(-4, 3, 400).astype(np.float32)
    p = sc.paper_curve(y)
    assert np.all(np.diff(p) >= 0)
    assert p.min() >= sc.PAPER_BLACK - 1e-6 and p.max() <= sc.PAPER_WHITE + 1e-6
    assert abs(float(sc.paper_curve(np.float32([0.0]))[0])) < 0.05     # mid grey stays mid grey


@pytest.mark.parametrize("values", [
    np.zeros((120, 180, 3), np.float32),                      # black: blank frame
    np.ones((120, 180, 3), np.float32),                       # clipped
    np.full((120, 180, 3), 0.3, np.float32),                  # uniform
    np.full((1, 1, 3), 0.3, np.float32),                      # one pixel
    np.random.default_rng(1).uniform(0.05, 0.5, (3, 600, 3)).astype(np.float32),   # long and thin
])
def test_odd_frames_render_without_errors(values):
    stats = sc.frame_stats(values)
    for auto in (False, True):
        params = sc.frame_params(stats, sc.roll_model([stats]), auto_print=auto)
        assert np.isfinite(sc.render(values, params, output_float=True)).all()
        assert sc.render(values, params).shape == values.shape


def test_display_encoded_sources_are_linearised(tmp_path):
    import tifffile
    from PIL import Image
    ramp = np.linspace(0.05, 0.9, 64, dtype=np.float32)
    encoded = np.where(ramp <= 0.0031308, ramp * 12.92, 1.055 * ramp ** (1 / 2.4) - 0.055)
    img8 = np.repeat(np.rint(np.tile(encoded, (8, 1)) * 255)[..., None], 3, axis=2).astype(np.uint8)
    Image.fromarray(img8).save(tmp_path / "scan.png")
    tifffile.imwrite(tmp_path / "scan8.tif", img8, photometric="rgb")
    tifffile.imwrite(tmp_path / "scan16.tif", np.rint(np.repeat(np.tile(ramp, (8, 1))[..., None], 3, 2) * 65535)
                     .astype(np.uint16), photometric="rgb")
    assert sc.is_display_encoded(str(tmp_path / "scan.png")) and sc.is_display_encoded(str(tmp_path / "scan8.tif"))
    assert not sc.is_display_encoded(str(tmp_path / "scan16.tif"))
    for name in ("scan.png", "scan8.tif", "scan16.tif"):
        values = sc.load_linear(str(tmp_path / name), True)
        np.testing.assert_allclose(values[0, :, 1], ramp, atol=0.006)   # linear light, whatever the file


def test_common_raw_formats_are_accepted():
    from smneg.flat_field import RAW_EXTENSIONS
    assert {".nef", ".raf", ".dng", ".cr2", ".cr3", ".arw", ".orf", ".rw2", ".pef"} <= RAW_EXTENSIONS


def test_film_base_reference_fixes_frames_without_a_rebate():
    st, li = STOCKS["Portra-like"], LIGHTS["D65"]
    frames, true_base = [], None
    for content in ("balanced", "warm", "cool"):
        refl, boxes, rebate = scene(content, np.random.default_rng(11), H, W, small_wedge=True)
        raw = expose(refl, rebate, st, li)
        true_base = np.median(raw[rebate], axis=0)
        b = int(0.04 * H) + 2                                       # tight crop: no rebate in the frame
        frames.append((raw[b:-b, b:-b], [(y0 - b, y1 - b, x0 - b, x1 - b) for y0, y1, x0, x1 in boxes]))
    leader = np.tile(true_base, (60, 90, 1)).astype(np.float32)
    leader *= np.random.default_rng(2).normal(1, 0.004, leader.shape).astype(np.float32)   # sensor noise
    base, spread, orange = sc.measure_film_base([leader, leader * np.float32(1.002)])
    assert np.abs(np.log10(base) - np.log10(true_base)).max() < 0.005
    assert spread < 0.08 and orange < sc.ORANGE_MASK
    stats = [sc.frame_stats(c) for c, _ in frames]
    chroma = {}
    for name, reference in (("estimated", None), ("reference", base)):
        roll = sc.roll_model(stats, reference=reference)
        lab = [grey_lab(c, sc.frame_params(s, roll), box) for (c, box), s in zip(frames, stats)]
        chroma[name] = np.mean([np.hypot(x[:, 1], x[:, 2]).mean() for x in lab])
    assert chroma["reference"] < 3.0 and chroma["reference"] < chroma["estimated"] / 3   # measured 2.6 against ~10


def test_clipped_leader_scan_is_refused():
    with pytest.raises(ValueError):
        sc.measure_film_base([np.ones((50, 50, 3), np.float32)])


def test_roll_lock_prints_the_same_tone_the_same_in_every_frame():
    st, li = STOCKS["Portra-like"], LIGHTS["D65"]
    frames = []
    for content in ("balanced", "warm", "cool", "low-key", "high-key"):
        refl, boxes, rebate = scene(content, np.random.default_rng(11), H, W, small_wedge=True)
        frames.append((expose(refl, rebate, st, li), boxes))
    stats = [sc.frame_stats(r) for r, _ in frames]
    model = sc.roll_model(stats)
    spread = {}
    for name, meter in sc.METER_STRENGTHS.items():
        grey = [grey_lab(r, sc.frame_params(s, model, auto_print=True, meter=meter), boxes)[7, 0]
                for (r, boxes), s in zip(frames, stats)]
        spread[name] = np.ptp(grey)
    assert spread["roll"] < 1.0                                  # measured 0.0 (frame: 24)
    assert spread["roll"] < spread["balanced"] < spread["frame"]


def test_chroma_denoise_cuts_colour_noise_and_keeps_colours():
    st, li = STOCKS["Portra-like"], LIGHTS["D65"]
    refl, boxes, rebate = scene("balanced", np.random.default_rng(11), 480, 720)
    clean = expose(refl, rebate, st, li)
    noisy = np.clip(clean + np.random.default_rng(0).normal(0, 0.002, clean.shape).astype(np.float32), 1e-5, 1)
    stats = sc.frame_stats(noisy)
    params = sc.frame_params(stats, sc.roll_model([stats]), auto_print=True)
    a, b, c, d = boxes[10]

    def colour_noise(image):
        lab = srgb_to_lab(image[a:b, c:d].reshape(-1, 3).astype(np.float64))
        return np.hypot(lab[:, 1] - lab[:, 1].mean(), lab[:, 2] - lab[:, 2].mean()).mean(), lab.mean(0)

    raw_noise, raw_mean = colour_noise(sc.render(noisy, params, output_float=True, denoise=False))
    den_noise, den_mean = colour_noise(sc.render(noisy, params, output_float=True))
    assert den_noise < 0.6 * raw_noise                               # measured 6.4 -> 1.8
    assert np.abs(den_mean - raw_mean).max() < 1.0                   # the colour itself does not move
    cs = sc.frame_stats(clean)
    cp = sc.frame_params(cs, sc.roll_model([cs]), auto_print=True)
    untouched = np.abs(sc.render(clean, cp, output_float=True) - sc.render(clean, cp, output_float=True, denoise=False))
    assert untouched.mean() < 0.002                                  # a clean image is left alone
    flat = sc.frame_params(cs, sc.roll_model([cs]))                  # the flat master is never denoised
    np.testing.assert_array_equal(sc.render(clean, flat), sc.render(clean, flat, denoise=False))


def _print_params(density_range=1.5):
    bounds = np.array([[0.0] * 3, [density_range] * 3])
    return sc.FrameParams(base=np.ones(3, np.float32), slopes=np.ones(3, np.float32), anchor=0.0,
                          bounds=bounds, print_paper=True)


def test_camera_profile_with_auto_print_works_on_scene_exposure(tmp_path):
    """The profile's matrix is made for linear light. Auto print's values are toned, so the matrix is
    applied on scene exposure: the same colour at three brightness levels gets the same correction."""
    a = sc.load_camera_profile(str(_profile_file(tmp_path))).working_matrix()
    params = _print_params()
    scene = sc.print_scene_range(params)
    assert scene == pytest.approx(1.5 / sc.FILM_GAMMA)
    colour = np.array([0.25, -0.05, -0.2])                                    # log10 exposure against grey
    levels = np.array([-1.6, -1.1, -0.6])                                     # below the print's white
    scene_in = levels[:, None] + colour[None, :]
    log_e = sc.scene_to_print(scene_in, scene).astype(np.float32)[None]
    expected = np.log10(np.power(10.0, scene_in) @ a.T.astype(np.float64))
    for fast in (True, False):
        out = sc.render(None, params, log_e=log_e, camera_matrix=a, output_float=not fast, denoise=False)
        linear = sc.srgb_decode(out[0].astype(np.float64) / (255 if fast else 1))
        got = sc.print_to_scene(np.log10(linear / sc.MID_GREY), scene)
        np.testing.assert_allclose(got, expected, atol=0.03 if fast else 0.002)


def test_identity_camera_profile_changes_nothing_with_auto_print(portra):
    photos, _, stats, model = portra
    raw, _ = photos[0]
    params = sc.frame_params(stats[0], model, auto_print=True)
    assert params.print_paper
    for fast in (True, False):
        plain = sc.render(raw, params, output_float=not fast)
        same = sc.render(raw, params, output_float=not fast, camera_matrix=np.eye(3, dtype=np.float32))
        limit = 1 if fast else 2e-3
        assert np.abs(plain.astype(np.float64) - same.astype(np.float64)).max() <= limit


def test_greys_stay_neutral_with_camera_profile_and_auto_print(tmp_path):
    a = sc.load_camera_profile(str(_profile_file(tmp_path))).working_matrix()
    grey = np.repeat(np.linspace(-2.0, 0.6, 50, dtype=np.float32)[:, None], 3, axis=1)[None]
    for fast in (True, False):
        out = sc.render(None, _print_params(), log_e=grey, camera_matrix=a, output_float=not fast, denoise=False)
        lab = srgb_to_lab(out.reshape(-1, 3).astype(np.float64) / (1 if not fast else 255))
        assert np.hypot(lab[:, 1], lab[:, 2]).max() < 0.6


def _icc(curve: bytes) -> bytes:
    """A minimal ICC profile holding only a green tone curve."""
    import struct
    table = struct.pack(">I", 1) + b"gTRC" + struct.pack(">II", 144, len(curve))
    return bytes(128) + table + curve


def _gamma_curve(gamma):
    import struct
    return b"curv" + bytes(4) + struct.pack(">IH", 1, round(gamma * 256))


def test_icc_tone_curves_are_read():
    import struct
    x = np.arange(sc.TRANSFER_STEPS + 1) / sc.TRANSFER_STEPS
    np.testing.assert_allclose(sc.icc_transfer(_icc(_gamma_curve(2.2))), x ** (563 / 256), atol=1e-6)
    np.testing.assert_allclose(sc.icc_transfer(_icc(b"curv" + bytes(4) + struct.pack(">I", 0))), x, atol=1e-6)
    sampled = b"curv" + bytes(4) + struct.pack(">I", 3) + struct.pack(">3H", 0, 16384, 65535)
    assert sc.icc_transfer(_icc(sampled))[sc.TRANSFER_STEPS // 2] == pytest.approx(16384 / 65535, abs=1e-4)
    fixed = lambda *values: b"".join(struct.pack(">i", round(v * 65536)) for v in values)
    srgb = b"para" + bytes(4) + struct.pack(">HH", 3, 0) + fixed(2.4, 1 / 1.055, 0.055 / 1.055, 1 / 12.92, 0.04045)
    np.testing.assert_allclose(sc.icc_transfer(_icc(srgb)), sc.srgb_decode(x), atol=2e-4)
    assert sc.icc_transfer(b"not a profile") is None
    assert sc.icc_transfer(_icc(b"mft2" + bytes(40))) is None            # look-up-table profile: not used


def test_embedded_profile_decides_how_a_scan_is_linearized(tmp_path):
    """A 16-bit TIFF with a gamma profile and a JPEG with an Adobe RGB-like curve are not taken as linear /
    sRGB: they give the same linear values as their untagged twins."""
    import tifffile
    from PIL import Image, ImageCms
    ramp = np.linspace(0.05, 0.9, 64)
    tile = lambda values, dtype, top: np.rint(np.repeat(np.tile(values, (8, 1))[..., None], 3, 2) * top).astype(dtype)
    gamma = 563 / 256
    tifffile.imwrite(tmp_path / "gamma16.tif", tile(ramp ** (1 / gamma), np.uint16, 65535), photometric="rgb",
                     iccprofile=_icc(_gamma_curve(2.2)))
    tifffile.imwrite(tmp_path / "linear16.tif", tile(ramp, np.uint16, 65535), photometric="rgb",
                     iccprofile=_icc(_gamma_curve(1.0)))
    srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    tifffile.imwrite(tmp_path / "srgb16.tif", tile(sc.srgb_encode(ramp), np.uint16, 65535), photometric="rgb",
                     iccprofile=srgb)
    Image.fromarray(tile(ramp ** (1 / gamma), np.uint8, 255)).save(tmp_path / "adobe.png", icc_profile=_icc(_gamma_curve(2.2)))
    assert sc.input_transfer(str(tmp_path / "linear16.tif")) is None
    for name, tolerance in (("gamma16.tif", 2e-4), ("linear16.tif", 2e-5), ("srgb16.tif", 3e-4), ("adobe.png", 0.006)):
        values = sc.load_linear(str(tmp_path / name), True)
        np.testing.assert_allclose(values[0, :, 1], ramp, atol=tolerance, err_msg=name)
