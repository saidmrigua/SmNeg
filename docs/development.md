<!-- SPDX-License-Identifier: Apache-2.0 | Copyright 2026 Said Mrigua -->
# Development guide

## Set up
```bash
git clone https://github.com/saidmrigua/SmNeg.git && cd SmNeg
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[tiff,dev]"
QT_QPA_PLATFORM=offscreen pytest -q                    # Windows PowerShell: $env:QT_QPA_PLATFORM="offscreen"
python -m pyflakes src tests packaging
```

## Layout
```
src/smneg/      the package (module map in how-it-works.md)
tests/          pytest; tests/data/engine_golden.npz = reference outputs of the inversion engine
docs/           documentation (docs/README.md is the index)
packaging/      PyInstaller spec, launcher, macOS icon script
.github/        CI, release workflow, issue and pull request templates
```

## The one rule: do not change the inversion math
`OfficialFilmEngine.load_negative_base` in `engine.py` defines how a negative becomes a positive. Users' archives were
graded with it, so its output must stay the same. `tests/test_engine_golden.py` compares it with stored reference outputs
(`rtol=1e-5`). If you must change it, discuss it in an issue first, explain why in the pull request, and regenerate the
golden file deliberately. Refactors must be bit-identical.

## Tests
| File | Covers |
|---|---|
| `test_engine_golden.py` | inversion against reference outputs (both code paths), exact parallel == sequential, unreadable files |
| `test_pipeline.py` | color pipeline (CMY, density, contrast, saturation, geometry) |
| `test_crop_flat.py` | crop and flat-field gain |
| `test_names.py` | filename templates and sequence numbers |
| `test_session.py`, `test_settings.py` | session files, settings migration (hermetic, unique organization names) |
| `test_tiff.py` | 16-bit TIFF export and XMP |
| `test_input_formats.py` | 16-bit TIFF input precision, preview size, EXIF orientation |
| `test_crop_orientation.py` | crop box and straighten angle follow the picture when rotation / mirror change (all 64 combinations) |
| `test_session_validation.py` | rejects valid JSON with a wrong structure |
| `test_versions.py` | version numbers agree across files |
| `test_hot_folder.py` | hot folder watching |

The interface itself (`window.py`, `views.py`, dialogs, the export loop) has no automated GUI tests; the release workflow
only starts each built app offscreen as a smoke test.
Check it by hand with a real RAW
folder before a release: grid, enlarged view, zoom, crop, undo, PASS, export JPEG and TIFF, session information.

## Code style
- English only in the UI, comments and docs. Every source file starts with
  `# SPDX-License-Identifier: Apache-2.0` and `# Copyright 2026 Said Mrigua` (keep your own line if you add a significant
  contribution).
- `pyflakes` must be clean. Keep functions small; `window.py` is too large and is a good target for splitting
  (needs GUI testing, see the [changelog](../CHANGELOG.md)).
- No network calls, no telemetry, no secrets.

## Adding something
- **Keyboard shortcut**: add it in `window.py` and in the list in `help.py`; update `docs/shortcuts.md` to match.
- **Export preset**: `ExportDialog.PRESETS` in `export.py`; document it in [file-formats.md](file-formats.md).
- **Setting**: use `app_settings()`; keep old keys readable.
