# Changelog

## 0.2.0 - 2026-11-10
Answer to the community's IT8 test of 0.1.0 (see `AUDIT_REPORT.md`): a new, measured inversion engine.

- **Scientific engine** (new default for new sessions; `ENGINE` menu next to the tone profile):
  measured film base (rebate auto-detection, bare light and film holder rejected), density above base,
  roll-level neutral balance of the three dye layers, partial auto-exposure, printer lights in log exposure
  (1 point = 0.025 log E), scene-referred tone with a soft highlight shoulder, sRGB output.
  B&W negatives are detected and rendered neutral. Sessions saved earlier keep the Classic engine.
- **Film base reference**: measure the base on 1–3 scans of clear film (the roll's leader); used for the
  whole roll, saved with the session. Fixes the colour cast of tight 35 mm scans without a visible rebate.
- A detected rebate must be a strip along a side of the frame with the roll's colour; bright picture
  areas at an edge (sky, wall) are no longer taken for the film base.
- **Grey picker** (`N`) and **film-base picker** (`B`, `⇧B` = automatic) in the enlarged view; work at any
  rotation, crop, straightening or zoom. The picked base is saved with the session and used by the roll.
- **Auto print** (Scientific engine, on by default, `L`): automatic neutral print exposure and contrast
  per frame (split grade + paper toe/shoulder), black to white like a lab printer; off = flat master.
- **Several grey picks** (`N` again on a lighter or darker grey, `⇧N` clears): also corrects the tilt
  between the dye layers, i.e. casts in the highlights or shadows.
- **Roll balance**: save the dye balance measured on a full roll as a film profile and reuse it on short
  rolls or single frames of the same film (`FILM` menu).
- Auto print smooths the colour noise it amplifies (edge-aware, brightness and grain untouched).
- **Meter** choice for Auto print: Frame, Balanced (default) or Roll lock (one print setting for the roll).
- B&W detection no longer mistakes a colourless colour frame (plain sky) for B&W: a base with the
  orange mask is always colour film.
- **Film profile** (`FILM` button): calibrate a film + rig from a ColorChecker photographed on the film
  (4 clicks): density crosstalk matrix, dye-layer slopes and film contrast; saved, reusable, per session.
  See `docs/calibration.md`.
- RAW decoding pins LibRaw's scale (`adjust_maximum_thr=0`): every frame of a roll on the same scale.
- **Camera profile** (`CAMERA` button): loads an IT8 profile report from `it8_profiler` (camera + light),
  applied by the Scientific engine in linear light, neutral-preserving; saved with the session.
- Color keys range ±50 (was ±20) to leave room for picked corrections.
- Exports (JPEG and 16-bit TIFF) embed an sRGB ICC profile. `tifffile` is now a required dependency.
- Info bar shows the C/M/Y/D values and how the film base was found.
- Sharpness radius follows the image size, so the export matches the preview.
- HOLD no longer reverts color/density edits; turning HOLD on is a single undoable step.
- Camera RAW from Canon, Sony, Olympus/OM, Panasonic, Pentax and the other formats LibRaw reads
  (0.1.0 accepted only Nikon, Fujifilm and DNG).
- JPEG, PNG and 8-bit TIFF scans are decoded as sRGB-encoded values (they were treated as linear).
- Folder import decodes previews in parallel (about 2.5× faster) and lists the files it could not read.
- A blank (black) frame on a roll no longer breaks the roll analysis.
- Version defined once (`src/smneg/__init__.py`); the sdist includes the tests and their data.
- NOTICE describes the libraries bundled in the pre-built apps; their license files ship inside the apps.
- Remaining French interface strings translated.
- Accuracy tests (`tests/test_scientific.py`, `tests/test_film_profile.py`) and an audit harness
  (`tests/audit/`). 133 tests.

## 0.1.0 - first public release
SMneg is the open-source release of an existing in-house film-negative inversion tool
(previously an unreleased "Frontier SP-500 Master v6" controller).

- Renamed to **SMneg**; removed third-party brand names from the UI. The English UI replaces the French one.
- Settings migrate automatically from the old settings store; sessions created by earlier versions still open.
- Windows support: capture is disabled outside macOS, keyboard hints show Ctrl/Alt/Shift.
- Export: pipelined (load next / render / write previous), "Current frame" button, session information
  filled in once at *New Session* and reused by the export dialog, filename templates with variables.
- 16-bit TIFF export with embedded XMP metadata (needs `tifffile`).
- Undo/redo, in-place zoom with full-resolution decoding, shortcuts help (F1).
- The negative inversion algorithm is unchanged; a regression test compares it with reference outputs.
