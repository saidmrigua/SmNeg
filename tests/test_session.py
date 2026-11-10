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
