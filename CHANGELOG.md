# Changelog

All notable changes are listed here. Format based on [Keep a Changelog](https://keepachangelog.com/),
versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]
### Planned
- Split `window.py` into smaller modules (needs GUI testing).
- Code signing / notarization of the macOS app and signing of the Windows app.
- Real-hardware testing on Windows.

## [0.2.0] - 2026-11-10
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
- Accuracy tests (`tests/test_scientific.py`, `tests/test_film_profile.py`) and an audit harness
  (`tests/audit/`).


## [0.1.0] - 2026-11-08
Refreshed first release: includes the corrections below, with the original release archived.

### Fixed
- A manual crop now stays on the same part of the picture when you rotate or mirror the frame (before, the crop box
  stayed at the same place on screen and framed something else). The straighten angle follows too, also when frames
  receive rotation / mirror through Copy-Paste or Hold. Crops saved by earlier versions are read as they were.
- 16-bit TIFF input is decoded without being reduced to 8 bits first (the inversion formulas are unchanged;
  8-bit TIFF, JPEG, PNG and RAW inputs give the same results as before).
- Export no longer writes a preview-resolution image when the full-resolution decode fails: that frame is listed as
  *not exported* and nothing is written for it.
- Session files are validated (structure and types) before use; a file with valid JSON but the wrong structure now gives a
  clear error instead of failing later.
- Three remaining French status messages are now English.

### Added
- Creator attribution in the app and Windows executable; LICENSE, NOTICE and third-party notices in native bundles.
- Offscreen Qt workflow tests; 221 tests pass.
- An explicit first-release refresh mode keeps the tag, source archives and downloadable packages consistent, with a backup of the previous release.
- Release workflow: tests must pass on macOS and Windows before anything is built; each app runs a start-up
  self-test; the macOS app is labelled arm64 (`SMneg-macOS-arm64.dmg`) and the Windows app `SMneg-Windows-x64.zip`.
- CI installs the wheel and the sdist into a clean environment; `tests/test_versions.py` keeps version numbers in sync.
- Tests for 16-bit TIFF precision and orientation, session validation, exact parallel/sequential equality and unreadable files.

### Initial public release
First public release. SMneg is the open-source version of an existing in-house film-negative inversion tool
(previously an unreleased "Frontier SP-500 Master v6" controller).

### Added
- Tests (44) including a golden test that pins the inversion engine to reference outputs; CI on macOS and Windows.
- Documentation (`docs/`), screenshots, GitHub Release with macOS `.dmg`, Windows `.zip`, wheel and sdist.
- Session information at *New Session*, with presets, autocomplete and validation; it pre-fills the export dialog.
- Export: JPEG (8-bit) and TIFF (16-bit, XMP), filename templates with variables, `metadata.json`, a pipelined
  exporter, a *Current frame* button.
- Undo/redo, in-place zoom with full-resolution decoding, flat-field correction, shortcuts help (F1).

### Changed
- Renamed to **SMneg**; the UI is now English and brand names were removed from it.
- A larger, centered **PASS** mark on skipped frames.
- Settings migrate automatically from the old settings store; sessions from earlier versions still open.
- Windows support: capture is disabled outside macOS and keyboard hints show Ctrl/Alt/Shift.

### Unchanged
- The negative inversion algorithm (`load_negative_base`) is identical to the original.

[Unreleased]: https://github.com/saidmrigua/SmNeg/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/saidmrigua/SmNeg/releases/tag/v0.1.0
