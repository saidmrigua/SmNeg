# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
import json

from smneg.session import LEGACY_PROJECT_FILE, PROJECT_FILE, project_path, read_project, write_project


def test_roundtrip_with_session_info(tmp_path):
    info = {"shoot_title": "Wedding", "city": "Fes"}
    write_project(tmp_path, [], 0, 0, {}, "", info)
    assert (tmp_path / PROJECT_FILE).is_file()
    assert read_project(tmp_path)["session_info"] == info


def test_info_defaults_to_empty(tmp_path):
    write_project(tmp_path, [], 0, 0, {}, "")
    assert read_project(tmp_path)["session_info"] == {}


def test_legacy_project_file_is_still_read(tmp_path):
    (tmp_path / LEGACY_PROJECT_FILE).write_text(json.dumps({"frames": [], "current_idx": 0, "view": 0}))
    assert project_path(tmp_path).name == LEGACY_PROJECT_FILE
    assert read_project(tmp_path)["frames"] == []


import pytest
from smneg.session import validate_session


@pytest.mark.parametrize('data', [[], None, {'frames': {}}, {'frames': [{}]},
    {'current_idx': '0'}, {'view': 2}, {'session_info': []},
    {'session_info': {'film': 123}}, {'flat_field_reference': None},
    {'frames': [{'path': 'x', 'contrast': float('nan')}]},
    {'frames': [{'path': 'x', 'mirror': 'false'}]},
    {'frames': [{'path': 'x', 'manual_crop': [0.8, 0, 0.2, 1]}]}])
def test_invalid_session_schema_rejected(data):
    with pytest.raises(ValueError, match='Invalid session'):
        validate_session(data)


def test_read_invalid_project_rejects_before_activation(tmp_path):
    (tmp_path / PROJECT_FILE).write_text('[]')
    with pytest.raises(ValueError):
        read_project(tmp_path)
