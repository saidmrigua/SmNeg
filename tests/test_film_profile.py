# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
"""Film profile: density crosstalk + dye slopes + contrast fitted on a ColorChecker shot on film."""
import numpy as np
import pytest

from film_chart import chart_negative

from smneg import film_profile as fp
from smneg import scientific as sc


@pytest.mark.parametrize("stock, light", [("Portra-like", "D65"), ("Ektar-like", "LED")])
def test_fit_reduces_chart_error_and_finds_the_film(stock, light):
    raw, centres, base, pitch = chart_negative(stock, light)
    profile = fp.fit_film_profile(fp.sample_patches(raw, centres, pitch * 0.25), base)
    assert profile.delta_e_after < 0.6 * profile.delta_e_before       # measured 4.9 -> 2.3, 7.8 -> 3.7
    assert profile.delta_e_after < 4.0
    assert profile.grey_chroma_after < 1.5
    true_gamma = {"Portra-like": 0.60, "Ektar-like": 0.74}[stock]
    assert abs(profile.gamma - true_gamma) < 0.08
    np.testing.assert_allclose(np.asarray(profile.matrix).sum(1), 1, atol=1e-6)


def test_orientation_is_found_from_corners_in_any_order():
    raw, centres, base, pitch = chart_negative()
    for order in ([0, 5, 23, 18], [23, 0, 18, 5], [18, 23, 5, 0]):
        found, _ = fp.best_layout(raw, centres[order], base, pitch * 0.25)
        np.testing.assert_allclose(found, centres, atol=1)


def test_unmix_keeps_greys_and_identity_is_neutral():
    grey = np.full((4, 4, 3), 0.3, np.float32)
    matrix = np.array([[1.2, -0.1, -0.1], [-0.2, 1.3, -0.1], [-0.3, -0.2, 1.5]], np.float32)
    np.testing.assert_allclose(fp.unmix(grey, matrix), grey, rtol=1e-5)
    colour = np.random.default_rng(1).uniform(0.05, 0.9, (8, 8, 3)).astype(np.float32)
    np.testing.assert_allclose(fp.unmix(colour, np.eye(3)), colour, rtol=1e-5)


def test_profile_round_trip_and_validation(tmp_path):
    raw, centres, base, pitch = chart_negative()
    profile = fp.fit_film_profile(fp.sample_patches(raw, centres, pitch * 0.25), base, name="Portra test")
    loaded = fp.load_film_profile(profile.save(tmp_path / "p.json"))
    assert loaded.name == "Portra test" and loaded.matrix == profile.matrix and loaded.gamma == profile.gamma
    bad = tmp_path / "bad.json"
    bad.write_text('{"kind": "smneg-film-profile", "matrix": [[1,0,0],[0,1,0],[0,0,0]], "slopes": [1,1,1], "gamma": 0.6}')
    with pytest.raises(ValueError):
        fp.load_film_profile(bad)


def test_engine_with_film_profile_renders_the_chart_more_accurately():
    raw, centres, base, pitch = chart_negative("Portra-like", "LED")
    profile = fp.fit_film_profile(fp.sample_patches(raw, centres, pitch * 0.25), base)
    reference = fp.reference_lab_d65()

    def chart_error(values, film):
        stats = sc.frame_stats(values)
        params = sc.frame_params(stats, sc.roll_model([stats], film), film)
        out = sc.render(values, params, output_float=True).astype(np.float64)
        rgb = fp.sample_patches(out, centres, pitch * 0.25)
        linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
        lab = fp.linear_srgb_to_lab(linear)
        best = min(np.mean(fp.delta_e2000(lab + [d, 0, 0], reference, k_l=2.0)) for d in range(-30, 31))
        return best, np.hypot(lab[fp.GREYS, 1], lab[fp.GREYS, 2]).mean()

    auto_de, auto_grey = chart_error(raw, None)
    film_de, film_grey = chart_error(raw, profile)
    assert film_de < auto_de
    assert film_grey < 1.5
