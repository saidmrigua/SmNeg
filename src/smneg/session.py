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


_FRAME_TYPES = {
    "cyan": int, "magenta": int, "yellow": int, "density": int, "rotation": int, "sharpness": int,
    "contrast": float, "saturation": float, "straighten": float,
    "mirror": bool, "auto_crop": bool, "show_clipping": bool, "is_passed": bool,
    "processed_date": str, "tone_profile": str, "auto_print": bool,
}


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check(condition, message):
    if not condition:
        raise ValueError(f"Invalid session file: {message}")


def _is_rgb(value):
    """Three positive linear values (a film base or a grey pick measured on the scan)."""
    return (isinstance(value, (list, tuple)) and len(value) == 3
            and all(_is_number(v) and math.isfinite(v) and 0 < v <= 2 for v in value))


def _is_print_lock(value):
    """Print settings pasted from another frame: see FrameItem.print_lock."""
    def numbers(item, count):
        return (isinstance(item, (list, tuple)) and len(item) == count
                and all(_is_number(v) and math.isfinite(v) for v in item))
    if not isinstance(value, dict) or not _is_number(value.get("anchor")) or not math.isfinite(value["anchor"]):
        return False
    bounds, balance = value.get("bounds"), value.get("balance")
    return ((bounds is None or (isinstance(bounds, (list, tuple)) and len(bounds) == 2
                                and all(numbers(row, 3) for row in bounds)))
            and (balance is None or numbers(balance, 4)))


def validate_session(data):
    """Check the structure and types of a session before it is used; raises ValueError with a clear message.
    Unknown keys are ignored so that newer files still open."""
    _check(isinstance(data, dict), "the top level must be an object")
    frames = data.get("frames", [])
    _check(isinstance(frames, list), '"frames" must be a list')
    for number, frame in enumerate(frames, start=1):
        _check(isinstance(frame, dict), f"frame {number} must be an object")
        _check(isinstance(frame.get("path"), str) and frame["path"], f'frame {number} needs a "path" text')
        for key, kind in _FRAME_TYPES.items():
            if key not in frame:
                continue
            value = frame[key]
            ok = (_is_number(value) if kind is float
                  else isinstance(value, int) and not isinstance(value, bool) if kind is int
                  else isinstance(value, kind))
            _check(ok, f'frame {number}: "{key}" has the wrong type')
        _check(frame.get("rotation", 0) % 90 == 0, f'frame {number}: "rotation" must be a multiple of 90')
        base_pick = frame.get("base_pick")
        _check(base_pick is None or _is_rgb(base_pick), f'frame {number}: "base_pick" must be three positive numbers')
        picks = frame.get("grey_picks")
        _check(picks is None or (isinstance(picks, list) and len(picks) <= 8 and all(map(_is_rgb, picks))),
               f'frame {number}: "grey_picks" must be a short list of RGB values')
        lock = frame.get("print_lock")
        _check(lock is None or _is_print_lock(lock), f'frame {number}: "print_lock" is not valid')
        crop = frame.get("manual_crop")
        _check(crop is None or (isinstance(crop, (list, tuple)) and len(crop) == 4 and all(map(_is_number, crop))),
               f'frame {number}: "manual_crop" must be four numbers')
    current = data.get("current_idx", 0)
    _check(isinstance(current, int) and not isinstance(current, bool), '"current_idx" must be an integer')
    for key in ("session_info", "camera_reference"):
        _check(isinstance(data.get(key, {}), dict), f'"{key}" must be an object')
    reference = data.get("flat_field_reference")
    _check(reference is None or isinstance(reference, str), '"flat_field_reference" must be text')
    _check(data.get("engine", "classic") in ENGINES, '"engine" is unknown')
    _check(data.get("meter", "balanced") in METERS, '"meter" is unknown')
    for key in ("camera_profile", "film_profile"):
        _check(isinstance(data.get(key, ""), str), f'"{key}" must be a file path')
    film_base = data.get("film_base_reference")
    _check(film_base is None or (
        isinstance(film_base, dict) and isinstance(film_base.get("files", []), list)
        and all(isinstance(path, str) for path in film_base.get("files", [])) and _is_rgb(film_base.get("base"))
    ), '"film_base_reference" is invalid')
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
