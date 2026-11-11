# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
"""The built app's --self-test checks both engines and the exports; the same check runs here."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_self_test_engine_check_passes(tmp_path):
    spec = importlib.util.spec_from_file_location("smneg_launcher", ROOT / "packaging" / "launcher.py")
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    assert launcher.check_engines(tmp_path) is None
