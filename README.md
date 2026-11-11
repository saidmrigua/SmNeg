<div align="center">

<img src="src/smneg/assets/icon.png" width="96" alt="SMneg icon">

# SMneg

<sub>FREE &amp; OPEN SOURCE · V0.2.0 · SMNEG = SAID MRIGUA NEGATIVE</sub>

## From negative to picture.

SMneg inverts film negatives you photograph with a digital camera.<br>
RAW or 16-bit TIFF in, lab-style printer-lights color, full-resolution JPEG or 16-bit TIFF out.

[![Download for macOS](https://img.shields.io/badge/Download%20for%20macOS-Apple%20Silicon%20·%20.dmg-E8912D?style=for-the-badge&logo=apple&logoColor=white)](https://github.com/saidmrigua/SmNeg/releases/latest/download/SMneg-macOS-arm64.dmg)
[![Download for Windows](https://img.shields.io/badge/Download%20for%20Windows-64--bit%20·%20.zip-E8912D?style=for-the-badge)](https://github.com/saidmrigua/SmNeg/releases/latest/download/SMneg-Windows-x64.zip)

[![CI](https://github.com/saidmrigua/SmNeg/actions/workflows/ci.yml/badge.svg)](https://github.com/saidmrigua/SmNeg/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![Platforms](https://img.shields.io/badge/platforms-macOS%20%7C%20Windows-lightgrey)

<sub>The apps are not code-signed: your system asks for confirmation the first time. <a href="#install">How to open them</a> · <a href="https://github.com/saidmrigua/SmNeg/releases/latest">Release notes &amp; checksums</a></sub>

<img src="docs/images/hero.jpg" width="820" alt="Color photograph of a traditional Moroccan water seller in a red outfit walking among pigeons on a palm-lined square, converted from a film negative with SMneg">

<sub>Camera scan, converted with SMneg (S Curve tone). No retouching. Photograph © Said Mrigua.</sub>

**[Website](https://smneg.saidmrigua.com/)** · **[Before / After](#before--after)** · **[Features](#what-it-does)** · **[Demo](#see-it-in-action)** · **[Tutorial](#tutorial)** · **[Install](#install)** · **[Documentation](#documentation)** · **[License](#license)**

<sub>Created and developed by <b>Said Mrigua</b> · Copyright © 2026 Said Mrigua</sub>

</div>

---

## Before / After

<sub>ELEVEN FRAMES FROM ONE ROLL</sub>

**The negative as photographed, and the result.** Nikon Z8 camera scans of one roll, converted with SMneg using the
S Curve tone profile. No other adjustments, no retouching.

| Negative | SMneg |
|:---:|:---:|
| <img src="docs/images/before-after/06-negative.webp" width="420" alt="Boats and fishing nets, the negative"> | <img src="docs/images/before-after/06-smneg.webp" width="420" alt="Boats and fishing nets, after conversion with SMneg"> |
| <img src="docs/images/before-after/04-negative.webp" width="420" alt="Water seller and pigeons, the negative"> | <img src="docs/images/before-after/04-smneg.webp" width="420" alt="Water seller and pigeons, after conversion with SMneg"> |
| <img src="docs/images/before-after/09-negative.webp" width="420" alt="Stacked colored crates, the negative"> | <img src="docs/images/before-after/09-smneg.webp" width="420" alt="Stacked colored crates, after conversion with SMneg"> |
| <img src="docs/images/before-after/01-negative.webp" width="420" alt="Round building on a square, the negative"> | <img src="docs/images/before-after/01-smneg.webp" width="420" alt="Round building on a square, after conversion with SMneg"> |

<details>
<summary><b>Show the seven other frames</b></summary>
<br>

| Negative | SMneg |
|:---:|:---:|
| <img src="docs/images/before-after/03-negative.webp" width="420" alt="Sitting on the square, the negative"> | <img src="docs/images/before-after/03-smneg.webp" width="420" alt="Sitting on the square, after conversion with SMneg"> |
| <img src="docs/images/before-after/05-negative.webp" width="420" alt="Old facade and street lamp, the negative"> | <img src="docs/images/before-after/05-smneg.webp" width="420" alt="Old facade and street lamp, after conversion with SMneg"> |
| <img src="docs/images/before-after/07-negative.webp" width="420" alt="Nets drying, a dog asleep, the negative"> | <img src="docs/images/before-after/07-smneg.webp" width="420" alt="Nets drying, a dog asleep, after conversion with SMneg"> |
| <img src="docs/images/before-after/08-negative.webp" width="420" alt="Sign by the shore, the negative"> | <img src="docs/images/before-after/08-smneg.webp" width="420" alt="Sign by the shore, after conversion with SMneg"> |
| <img src="docs/images/before-after/11-negative.webp" width="420" alt="Shop doorway, the negative"> | <img src="docs/images/before-after/11-smneg.webp" width="420" alt="Shop doorway, after conversion with SMneg"> |
| <img src="docs/images/before-after/12-negative.webp" width="420" alt="Covered market, the negative"> | <img src="docs/images/before-after/12-smneg.webp" width="420" alt="Covered market, after conversion with SMneg"> |
| <img src="docs/images/before-after/13-negative.webp" width="420" alt="Water tank and dogs, the negative"> | <img src="docs/images/before-after/13-smneg.webp" width="420" alt="Water tank and dogs, after conversion with SMneg"> |

</details>

---

## What it does

<sub>BUILT FOR CAMERA SCANNING</sub>

<table>
<tr>
<td width="25%" valign="top">
<sub>IN</sub><br>
<b>RAW and 16-bit TIFF</b><br><br>
Nikon, Fujifilm, Canon, Sony, DNG and every other RAW format LibRaw reads. 16-bit TIFF keeps its full precision.
</td>
<td width="25%" valign="top">
<sub>COLOR</sub><br>
<b>Printer lights</b><br><br>
Correct like an analog enlarger or a lab scanner: cyan, magenta, yellow and density, one key per step.
</td>
<td width="25%" valign="top">
<sub>ROLL</sub><br>
<b>Whole-roll workflow</b><br><br>
Hot Folder import while you shoot, copy-paste and Hold, crop, rotate and mirror, undo for every change.
</td>
<td width="25%" valign="top">
<sub>OUT</sub><br>
<b>Full-resolution export</b><br><br>
JPEG or 16-bit TIFF with an sRGB profile, files named from your session, metadata embedded in every file.
</td>
</tr>
</table>

### New in 0.2.0: the Scientific engine

<table>
<tr>
<td width="25%" valign="top">
<sub>FILM BASE</sub><br>
<b>The orange mask, measured</b><br><br>
Found on the rebate, on scans of the clear leader, picked by hand (<kbd>B</kbd>) or shared by the roll.
</td>
<td width="25%" valign="top">
<sub>DENSITY</sub><br>
<b>A grey stays grey</b><br><br>
Density above base, the three dye layers balanced over the whole roll. B&amp;W film is detected and kept neutral.
</td>
<td width="25%" valign="top">
<sub>AUTO PRINT</sub><br>
<b>Exposure and contrast</b><br><br>
Set for each frame like a lab printer (<kbd>L</kbd>), with the roll's colour. Off: a flat 1:1 master.
</td>
<td width="25%" valign="top">
<sub>PROFILES</sub><br>
<b>Calibrate your film</b><br><br>
Grey picker (<kbd>N</kbd>), film profile from a ColorChecker on film, camera profile from an IT8 target.
</td>
</tr>
</table>

The Classic engine of 0.1.0 is still there, unchanged, for comparison and for older sessions.
How both engines work: [docs/how-it-works.md](docs/how-it-works.md).

---

## See it in action

<sub>OPEN, CORRECT, EXPORT. ONE MINUTE.</sub>

<div align="center">

<a href="docs/media/smneg-demo.mp4"><img src="docs/images/demo.gif" width="820" alt="Screen recording of SMneg: open a roll, rotate, correct with printer lights, copy and paste across the roll, export"></a>

<sub><a href="docs/media/smneg-demo.mp4"><b>▶ Watch the full demo video (MP4, 64 s)</b></a></sub>

</div>

Screen recording of the real app on six Nikon Z8 scans (recorded with SMneg 0.1.0): open the roll, rotate, S Curve and
printer-light correction, copy and paste across the roll, full-resolution export. Loading and export are sped up,
as marked on screen. The preview above plays at double speed. No sound.

---

## Tutorial

<sub>HOW SMNEG WORKS, IN TEN SLIDES</sub>

<table>
<tr>
<td width="50%"><img src="docs/images/tutorial/step-01.jpg" alt="Slide 1 of 10, How SMneg works: from the scan to the final file, with every keyboard shortcut"></td>
<td width="50%"><img src="docs/images/tutorial/step-02.jpg" alt="Slide 2 of 10, Step 01 Scan: photograph the negative in RAW on an even light source; expose to the right without clipping"></td>
</tr>
<tr>
<td><img src="docs/images/tutorial/step-03.jpg" alt="Slide 3 of 10, Step 02 Import: open a roll with Select Roll Folder, or let Hot Folder import each new RAW as you shoot"></td>
<td><img src="docs/images/tutorial/step-04.jpg" alt="Slide 4 of 10, The interface: toolbar, enlarged frame, per-frame C M Y D values and status, and the control panel"></td>
</tr>
<tr>
<td><img src="docs/images/tutorial/step-05.jpg" alt="Slide 5 of 10, Step 03 Correct: printer lights, Q/A cyan, W/S magenta, E/D yellow, arrow up/down density, T tone, R reset"></td>
<td><img src="docs/images/tutorial/step-06.jpg" alt="Slide 6 of 10, Step 04 The whole roll: Hold, copy and paste settings, crop and rotate, mark a frame Pass, undo any change"></td>
</tr>
<tr>
<td><img src="docs/images/tutorial/step-07.jpg" alt="Slide 7 of 10, Step 05 Export: export the roll with Cmd+E, JPEG or 16-bit TIFF at full resolution, named from the session"></td>
<td><img src="docs/images/tutorial/step-08.jpg" alt="Slide 8 of 10, Keyboard shortcuts: a keyboard map with every SMneg shortcut, colored by function"></td>
</tr>
<tr>
<td><img src="docs/images/tutorial/step-09.jpg" alt="Slide 9 of 10, Cheat sheet: all shortcuts grouped by color, density and tone, image, view, roll and export"></td>
<td><img src="docs/images/tutorial/step-10.jpg" alt="Slide 10 of 10, Your turn: try it on your next roll, free for macOS (Apple Silicon), Windows and Python"></td>
</tr>
</table>

<sub>The screenshots inside the slides and the video show the 0.1.0 window; the workflow and these shortcuts are the same in 0.2.0. The new keys
(<kbd>L</kbd> Auto print, <kbd>N</kbd> grey picker, <kbd>B</kbd> film base) are in <a href="docs/shortcuts.md">docs/shortcuts.md</a>,
and the step-by-step guide is <a href="docs/workflow.md">docs/workflow.md</a>.</sub>

### The app

![Grid view with six frames, two of them marked PASS](docs/images/ui-grid.png)

<sub>Grid view: six frames per page, printer-lights keys, density and tone controls. Frames marked PASS are skipped at export.</sub>

| Enlarged view | Export |
|---|---|
| ![Enlarged view](docs/images/ui-enlarged.png) | ![Export dialog](docs/images/ui-export.png) |

| Session information | Keyboard shortcuts |
|---|---|
| ![Session information dialog](docs/images/ui-session-info.png) | ![Keyboard shortcuts](docs/images/ui-shortcuts.png) |

---

## Install

<sub>REQUIREMENTS AND FIRST LAUNCH</sub>

<table>
<tr>
<td width="33%" valign="top">

**macOS**<br>
<sub>macOS 11+ · Apple Silicon (M1 or newer)</sub>

1. Open `SMneg-macOS-arm64.dmg` and drag SMneg to Applications.
2. macOS 14 and older: right-click the app, then *Open*.
3. macOS 15 and newer: *System Settings → Privacy & Security*, then *Open Anyway*.

Intel Mac: install from source.

**[Download .dmg](https://github.com/saidmrigua/SmNeg/releases/latest/download/SMneg-macOS-arm64.dmg)**

</td>
<td width="33%" valign="top">

**Windows**<br>
<sub>Windows 10/11 · 64-bit</sub>

1. Unzip `SMneg-Windows-x64.zip` anywhere.
2. Run `SMneg.exe` inside the folder. Keep the other files next to it.
3. If SmartScreen warns: *More info → Run anyway*.

The Windows interface has not been checked on real Windows hardware yet.

**[Download .zip](https://github.com/saidmrigua/SmNeg/releases/latest/download/SMneg-Windows-x64.zip)**

</td>
<td width="33%" valign="top">

**From source**<br>
<sub>Python 3.10+ · macOS, Windows</sub>

```bash
git clone https://github.com/saidmrigua/SmNeg.git
cd SmNeg
python -m venv .venv
source .venv/bin/activate
pip install -e .
smneg
```

<sub>Windows: <code>.venv\Scripts\activate</code>. Or install the wheel attached to the release.</sub>

**[Installation guide](docs/installation.md)**

</td>
</tr>
</table>

Allow several GB of RAM for 45 MP frames.

### Quick start
1. Click **NEW SESSION**, fill in the shoot information, then **Select Roll Folder** (or **HOT FOLDER**).
2. Adjust: <kbd>Q</kbd>/<kbd>A</kbd> <kbd>W</kbd>/<kbd>S</kbd> <kbd>E</kbd>/<kbd>D</kbd> color, <kbd>↑</kbd>/<kbd>↓</kbd> density. Press <kbd>P</kbd> to skip a frame.
3. <kbd>⌘E</kbd> exports the roll. Full walk-through: [docs/workflow.md](docs/workflow.md).

---

## In detail

- **Scientific engine** (default), see [How it works](docs/how-it-works.md):
  - the **film base** (orange mask) is measured on the rebate, on scans of the roll's clear leader
    (*film base reference*), picked by hand (`B`) or shared by the roll; bare light and the film holder are rejected
  - **density above base**, with the three dye layers balanced over the whole roll, so a grey stays grey
    whatever is in the frame; B&W negatives are detected and rendered neutral
  - **Auto print** (`L`): automatic exposure and contrast per frame, like a lab printer, with the colour of the
    roll; the meter can follow each frame, the whole roll, or a balance of both. Off: a flat 1:1 master
  - **grey picker** (`N`, one or several greys) and **film-base picker** (`B`) in the enlarged view
  - optional **film profile** calibrated from a ColorChecker photographed on the film (density crosstalk, dye
    balance, contrast; [Calibrating a film](docs/calibration.md)) and optional **camera profile** from an IT8
    transparency target
- **Classic engine**: the original 0.1.0 inversion (per-frame auto levels), kept for comparison and for older sessions
- **Files in**: camera RAW (`.nef .raf .dng .cr2 .cr3 .arw .orf .rw2 .pef` and the other formats LibRaw reads),
  8/16-bit TIFF, JPEG and PNG. An embedded ICC profile says how a file is encoded; without one, 8-bit files are
  taken as sRGB and 16-bit TIFF as linear
- **Files out**: JPEG 8-bit or TIFF 16-bit with an embedded sRGB ICC profile, EXIF/XMP metadata and an optional
  `metadata.json`; Photo Mechanic style filename templates (`{filenamebase}_{seqn}`). See [docs/file-formats.md](docs/file-formats.md)
- CMY / RGB color keys, density, contrast, saturation, tone profiles, sharpness, rotation, mirror, auto and manual crop
- In-place zoom with full-resolution decoding, flat-field (diffuser) correction, clipping preview
- Undo / redo, copy-paste settings (a pasted frame is printed like the copied one), Hold, 6-frame navigation,
  keyboard help on `F1`
- Sessions: enter client / film / copyright information once at *New Session*; it pre-fills the export dialog
- Hot Folder watching; on macOS, optional capture trigger for Nikon NX Tether

**Privacy.** Everything runs locally. Nothing is sent over the network and there are no accounts or API keys.
Settings use Qt's `QSettings` under the name *SMneg*; each session keeps its data in `smneg-session.json` in its folder
(older `frontier-session.json` files still open).

Built for photographers who scan film with a digital camera. The workflow will feel familiar to people
who have used Frontier-style scanning controllers. SMneg is an independent project, not affiliated
with FUJIFILM or Nikon (see [NOTICE](NOTICE)).

## Documentation
Start at the [documentation index](docs/README.md):
[installation](docs/installation.md) · [workflow](docs/workflow.md) · [shortcuts](docs/shortcuts.md) ·
[file formats and metadata](docs/file-formats.md) · [troubleshooting](docs/troubleshooting.md) ·
[how it works](docs/how-it-works.md) · [calibrating a film](docs/calibration.md) ·
[development](docs/development.md) · [releasing](docs/releasing.md) ·
[changelog](CHANGELOG.md) · [audit report](AUDIT_REPORT.md)

## Color accuracy, honestly
Version 0.1.0 was tested by the community on IT8 targets shot on film and had large grey errors (ΔE 5.8–21.5): its
"film base" step had no effect and density was shown as screen brightness. The full audit is in
[AUDIT_REPORT.md](AUDIT_REPORT.md). The Scientific engine is the answer to it. On the synthetic film model of
`tests/audit/audit_color.py` (Portra- and Ektar-like stocks, D65 and LED light), grey ΔE00 falls from 13–16 (0.1.0)
to 2.2–3.1 after one density setting, and to about 0.9 C* on the greys with a film profile. These are simulation
results: **measurements on real IT8 / ColorChecker targets shot on film are welcome** (open an issue with the scans).

## Status and limits
SMneg is in beta (0.2.0). It is used daily on macOS; Windows is expected to work but has not been
tested on real hardware yet (CI runs the tests and a start-up self-test of the built app on both).

| | macOS | Windows |
|---|---|---|
| Inversion, zoom, export | yes | expected to work |
| Nikon NX Tether capture button | yes (needs Accessibility permission) | disabled |
| Pre-built app | `.dmg` for Apple Silicon only (Intel: run from source), not notarized | `.zip` (64-bit), not signed |

- Automatic neutral balance without a film profile is estimated per roll; a slight cast can remain in the
  extreme highlights or shadows. Grey picks (`N`) or a film profile correct it.
- A camera profile (IT8 transparency) is exact for slides; for negatives it is an approximation, and a film
  profile (ColorChecker on film) is the more accurate correction. Using both at once is not recommended.
- Export is sRGB only (no Adobe RGB / ProPhoto yet). The app's windows are declared sRGB, so macOS shows the
  preview color-managed on wide-gamut displays.
- 45 MP class frames need several GB of RAM (zoom caches the last full-resolution frame).
- RAW demosaicing speed is bounded by LibRaw; the inversion itself is parallelized.
- `window.py` is large; splitting it is planned. Offscreen Qt tests cover crop, undo/redo, sessions and TIFF export; visual and real-camera checks remain manual.
- 0.2.0 was tested with PySide6 6.8 and 6.12, NumPy 2.2 to 2.5, Pillow 12 and 13, rawpy 0.26 to 0.28, OpenCV 4.10
  and 5.0, on Python 3.10, 3.12 and 3.13 (macOS, Apple silicon; Windows in CI); the bounds in `pyproject.toml` are conservative.

## Tests
```bash
pip install -e ".[dev]" && QT_QPA_PLATFORM=offscreen pytest -q
python tests/audit/audit_color.py        # color-accuracy report (Classic vs Scientific, synthetic film)
```
304 tests. `tests/test_scientific.py` and `tests/test_film_profile.py` measure color accuracy (grey ΔE, neutrality,
film base, B&W, scan-exposure invariance, preview = export); `tests/test_gui_scientific.py` drives the pickers, Auto print,
profiles and import through the real window. `tests/test_engine_golden.py` keeps the Classic engine unchanged; the others cover the
color pipeline, crop, flat-field, filename templates, sessions, settings migration, TIFF/XMP and the hot folder.
`tests/test_gui_workflow.py` exercises real Qt widgets with isolated temporary settings and synthetic scans.

## Contributing and support
Bug reports, ideas and pull requests are welcome: [CONTRIBUTING.md](CONTRIBUTING.md) ·
[open an issue](https://github.com/saidmrigua/SmNeg/issues/new/choose) · [code of conduct](CODE_OF_CONDUCT.md) ·
[security policy](SECURITY.md). To cite SMneg, see [CITATION.cff](CITATION.cff).

## License
**Code:** Apache License 2.0, Copyright © 2026 Said Mrigua. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
You may use, modify and share the code under that license, keeping the copyright and attribution notices.

**Photographs, video and tutorial slides** in `docs/images/` and `docs/media/` are © 2026 Said Mrigua, all rights
reserved. They are included to illustrate the software and may not be reused without permission.

Third-party libraries keep their own licenses: see [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
The pre-built apps contain them.

---

<div align="center">

**SMneg** · Created and developed by **Said Mrigua**, photographer, Morocco

Copyright © 2026 Said Mrigua · Code licensed under Apache-2.0 · Sample photographs © Said Mrigua, all rights reserved

[smneg.saidmrigua.com](https://smneg.saidmrigua.com/) · [saidmrigua.com](https://saidmrigua.com/) · [@mrigua_said](https://www.instagram.com/mrigua_said/) · [Source](https://github.com/saidmrigua/SmNeg) · [Releases](https://github.com/saidmrigua/SmNeg/releases) · [Report an issue](https://github.com/saidmrigua/SmNeg/issues)

</div>
