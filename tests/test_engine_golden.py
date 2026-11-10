# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
"""The inversion math must not change: compare with outputs produced by the original implementation."""
from pathlib import Path

import numpy as np
import pytest

from smneg import engine

DATA = np.load(Path(__file__).parent / "data" / "engine_golden.npz")
CASES = sorted(name[:-3] for name in DATA.files if name.endswith("_in"))


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("force_parallel", [False, True])
def test_inversion_matches_reference(case, force_parallel, monkeypatch):
    source = DATA[f"{case}_in"]
    monkeypatch.setattr(engine, "decode_negative", lambda path, full_resolution: source.copy())
    if force_parallel:
        monkeypatch.setattr(engine.OfficialFilmEngine, "PARALLEL_MIN_PIXELS", 0)
    result = engine.OfficialFilmEngine.load_negative_base("unused.tif")
    expected = DATA[f"{case}_out"]
    assert result.dtype == expected.dtype and result.shape == expected.shape
    np.testing.assert_allclose(result, expected, rtol=1e-5, atol=1e-6)


def test_parallel_result_is_bit_identical_to_sequential(monkeypatch):
    source = DATA[f"{CASES[0]}_in"]
    monkeypatch.setattr(engine, "decode_negative", lambda path, full_resolution: source.copy())
    sequential = engine.OfficialFilmEngine.load_negative_base("unused.tif")
    monkeypatch.setattr(engine.OfficialFilmEngine, "PARALLEL_MIN_PIXELS", 0)
    parallel = engine.OfficialFilmEngine.load_negative_base("unused.tif")
    assert np.array_equal(sequential, parallel)


def test_unreadable_source_returns_none_and_records_the_error(tmp_path):
    missing = str(tmp_path / "missing.nef")
    assert engine.OfficialFilmEngine.load_negative_base(missing, full_resolution=True) is None
    assert missing in engine.OfficialFilmEngine.errors
