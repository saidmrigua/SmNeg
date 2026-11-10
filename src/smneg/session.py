# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
import json
import math
from dataclasses import fields

from PySide6.QtCore import QSettings

from .settings import app_settings
from .models import FrameItem

SETTINGS_OK = QSettings.Status.NoError
ENGINES = ("scientific", "classic")
METERS = ("frame", "balanced", "roll")


FRAME_FIELDS = tuple(
    field.name for field in fields(FrameItem) if field.name not in {"index", "base_positive", "stats"}
)


def validate_session(data):
    """Reject invalid projects before callers change the active session."""
    def invalid(message):
        raise ValueError(f"Invalid session: {message}")

    if not isinstance(data, dict):
        invalid("expected a JSON object")
    frames = data.get("frames", [])
    if not isinstance(frames, list):
        invalid("frames must be a list")
    for key in ("current_idx", "view"):
        value = data.get(key, 0)
        if type(value) is not int or value < 0:
            invalid(f"{key} must be a nonnegative integer")
    if data.get("view", 0) not in (0, 1):
        invalid("unknown view")
    for key in ("session_info", "camera_reference"):
        if not isinstance(data.get(key, {}), dict):
            invalid(f"{key} must be an object")
    if any(not isinstance(value, str) for value in data.get("session_info", {}).values()):
        invalid("session information must contain text")
    if data.get("engine", "classic") not in ENGINES:
        invalid("unknown engine")
    for key in ("camera_profile", "film_profile"):
        if not isinstance(data.get(key, ""), str):
            invalid(f"{key.replace('_', ' ')} must be a file path")
    if data.get("meter", "balanced") not in METERS:
        invalid("unknown meter mode")
    reference = data.get("film_base_reference")
    if reference is not None and (
        not isinstance(reference, dict) or not isinstance(reference.get("files", []), list)
        or any(not isinstance(p, str) for p in reference.get("files", []))
        or not isinstance(reference.get("base"), list) or len(reference["base"]) != 3
        or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 < v <= 2 for v in reference["base"])
    ):
        invalid("invalid film base reference")
    if not isinstance(data.get("flat_field_reference", ""), str):
        invalid("flat-field reference must be text")
    defaults = FrameItem(0, "", None)
    for frame in frames:
        if not isinstance(frame, dict) or not isinstance(frame.get("path"), str) or not frame["path"]:
            invalid("each frame needs a nonempty path")
        for key in FRAME_FIELDS:
            if key not in frame:
                continue
            value, default = frame[key], getattr(defaults, key)
            if key == "grey_picks":
                if value is not None and (
                    not isinstance(value, list) or len(value) > 8
                    or any(not isinstance(p, (list, tuple)) or len(p) != 3
                           or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 < v <= 2 for v in p)
                           for p in value)
                ):
                    invalid("invalid grey picks")
            elif key == "base_pick":
                if value is not None and (
                    not isinstance(value, (list, tuple)) or len(value) != 3
                    or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 < v <= 2 for v in value)
                ):
                    invalid("invalid film base")
            elif key == "manual_crop":
                if value is not None and (
                    not isinstance(value, (list, tuple)) or len(value) != 4
                    or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in value)
                    or value[2] <= value[0] or value[3] <= value[1]
                ):
                    invalid("invalid crop rectangle")
            elif isinstance(default, bool):
                if type(value) is not bool:
                    invalid(f"{key} must be boolean")
            elif isinstance(default, (int, float)):
                if type(value) not in (int, float) or not math.isfinite(value):
                    invalid(f"{key} must be finite numeric data")
                if isinstance(default, int) and type(value) is not int:
                    invalid(f"{key} must be an integer")
            elif not isinstance(value, str):
                invalid(f"{key} must be text")
        if frame.get("contrast", 1) < 0 or frame.get("saturation", 1) < 0:
            invalid("contrast and saturation must be nonnegative")
    return data


def session_data(items, current_idx, view):
    return {
        "frames": [{key: getattr(item, key) for key in FRAME_FIELDS} for item in items],
        "current_idx": current_idx,
        "view": view,
    }


def save_session(items, current_idx, view, flat_reference="", info=None, engine=None, camera_profile=None,
                 film_profile=None, film_base_reference=None, meter=None):
    settings = app_settings()
    data = session_data(items, current_idx, view)
    if engine:
        data["engine"] = engine
    if camera_profile is not None:
        data["camera_profile"] = camera_profile
    if film_profile is not None:
        data["film_profile"] = film_profile
    if film_base_reference is not None:
        data["film_base_reference"] = film_base_reference
    if meter:
        data["meter"] = meter
    data["flat_field_reference"] = flat_reference
    data["session_info"] = info or {}
    settings.setValue("last_session", json.dumps(data))
    settings.sync()
    return settings.status() == SETTINGS_OK


def load_session():
    settings = app_settings()
    try:
        return validate_session(json.loads(settings.value("last_session", "{}", type=str)))
    except ValueError:
        return {}


def create_session_folder(parent):
    from datetime import date

    prefix = date.today().isoformat()
    for sequence in range(1, 10000):
        folder = parent / f"{prefix}_Session-{sequence:03d}"
        try:
            folder.mkdir()
        except FileExistsError:
            continue
        return folder
    raise OSError("Unable to create a unique session folder.")


PROJECT_FILE = "smneg-session.json"
LEGACY_PROJECT_FILE = "frontier-session.json"   # sessions created by earlier versions


def project_path(folder):
    legacy = folder / LEGACY_PROJECT_FILE
    return folder / PROJECT_FILE if (folder / PROJECT_FILE).is_file() or not legacy.is_file() else legacy


def write_project(folder, items, current_idx, view, camera_reference, flat_reference="", info=None, engine=None,
                  camera_profile=None, film_profile=None, film_base_reference=None, meter=None):
    data = session_data(items, current_idx, view)
    if engine:
        data["engine"] = engine
    if camera_profile is not None:
        data["camera_profile"] = camera_profile
    if film_profile is not None:
        data["film_profile"] = film_profile
    if film_base_reference is not None:
        data["film_base_reference"] = film_base_reference
    if meter:
        data["meter"] = meter
    data["camera_reference"] = camera_reference
    data["flat_field_reference"] = flat_reference
    data["session_info"] = info or {}
    temporary = folder / ".smneg-session.tmp"
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(folder / PROJECT_FILE)


def read_project(folder):
    return validate_session(json.loads(project_path(folder).read_text(encoding="utf-8")))
