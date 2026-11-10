# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
"""Valid JSON with the wrong structure must be rejected with a clear error, not crash later."""
import json

import pytest

from smneg import session

FRAME = {"path": "/scans/a.nef", "cyan": 1, "contrast": 1, "is_passed": False, "manual_crop": [0, 0, 1, 1]}


def test_valid_session_is_accepted():
    data = {"frames": [FRAME], "current_idx": 0, "view": 0, "session_info": {}, "flat_field_reference": None}
    assert session.validate_session(data) is data


def test_unknown_keys_are_ignored():
    session.validate_session({"frames": [{**FRAME, "future_option": 1}], "something_new": True})


@pytest.mark.parametrize("data", [
    [],
    "text",
    {"frames": "no"},
    {"frames": [[]]},
    {"frames": [{"cyan": 1}]},
    {"frames": [{"path": 5}]},
    {"frames": [{"path": "a", "cyan": "x"}]},
    {"frames": [{"path": "a", "cyan": True}]},
    {"frames": [{"path": "a", "is_passed": 1}]},
    {"frames": [{"path": "a", "rotation": 45}]},
    {"frames": [{"path": "a", "manual_crop": [1, 2]}]},
    {"frames": [], "current_idx": "0"},
    {"frames": [], "session_info": []},
    {"frames": [], "flat_field_reference": 3},
])
def test_invalid_structure_is_rejected(data):
    with pytest.raises(ValueError):
        session.validate_session(data)


def test_read_project_rejects_valid_json_with_bad_structure(tmp_path):
    (tmp_path / session.PROJECT_FILE).write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        session.read_project(tmp_path)


def test_read_project_rejects_malformed_json(tmp_path):
    (tmp_path / session.PROJECT_FILE).write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        session.read_project(tmp_path)


def test_read_project_round_trip(tmp_path):
    data = {"frames": [FRAME], "current_idx": 0}
    (tmp_path / session.PROJECT_FILE).write_text(json.dumps(data), encoding="utf-8")
    assert session.read_project(tmp_path) == data
