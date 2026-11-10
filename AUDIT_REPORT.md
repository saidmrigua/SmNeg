# SMneg audit report

Date: 2026-11-10 · Scope: `smneg_fixed/` (the most recent copy, 0.1.0 plus the TIFF, export, session and crop
repairs). It is compared with the original `../src/` where they differ. No application code was changed.
New files: `tests/audit/audit_color.py`, `tests/audit/audit_perf.py` and this report.

## Summary for a photographer

1. **The tester is right on the main points.** SMneg's "neutral" output is flat, but it is not accurate.
2. **The film base is never really used.** SMneg balances each colour channel from the *picture's own*
   brightest and darkest points. Measuring the real orange mask instead changes the result by 0.0000001.
   So colour depends on what is in the frame: the same grey card comes out with a different cast next to a
   blue sky or a red wall (measured: chroma up to 10 on a grey that should be 0).
3. **There is no real print curve.** SMneg shows the negative's *density* (a logarithmic quantity) directly
   as screen brightness. Mid-greys come out far too light (+28 L* in our test), highlights are squeezed
   together, and the darkest steps clip. No density or contrast key fixes this: the curve has the wrong shape.
4. **There is no colour management.** Camera RGB goes out as if it were sRGB, with no ICC profile in the files.
5. **Good news:** RAW decoding is correct (linear, 16-bit), scan exposure doesn't matter, the app is fast
   enough, and the code is small and readable. A ~40-line base-referenced prototype, run on the same data,
   reaches grey ΔE about 2, compared with 16 for SMneg (the Reddit table shows the same gap).
6. **The fix is a new engine core** (film base, then density, then print curve, then a defined colour space),
   not tuning. Your "flat, neutral, no auto-enhancement" goal fits this design well.
7. **One bug to fix right away:** with **HOLD** on, the colour and density keys are silently undone.
8. **I need from you:** IT8.7/2 negatives (Portra/Ektar NEFs) plus the target's reference `.txt`, so we can
   reproduce the Reddit numbers. The IT8 in `it8_profiler/data` is a Provia *slide*, so it can't test negatives.

## Progress since the audit (2026-11-10)

A new **Scientific engine** (`src/smneg/scientific.py`) is now the default for new sessions. Classic is
untouched and still selectable, and older sessions keep it. Measured with `tests/audit/audit_color.py`
section [8], on a synthetic roll of 15 photos plus a chart frame (Classic → Scientific):

| Roll | Grey ΔE00, default settings | Grey ΔE00, best single density | Grey C* across scenes, mean/max |
|---|---|---|---|
| Portra-like D65 | 16.0 → **4.1** | 6.0 → **3.1** | 2.7/5.7 → **2.1/2.6** |
| Portra-like LED | 16.0 → **5.1** | 6.0 → **2.3** | 1.8/3.9 → **1.5/1.8** |
| Ektar-like D65 | 13.3 → **4.1** | 4.9 → **2.8** | 2.5/4.7 → **1.8/2.5** |
| Ektar-like LED | 13.3 → **5.6** | 4.9 → **2.2** | 1.7/3.9 → **1.3/1.8** |

On real scans (NIG_TEST NEFs, two 120 RAF rolls, a B&W frame) the results are neutral and natural.
The rebate is detected on 10 of 11 RAF frames, and bare light and the film holder are rejected.

| Roadmap item | Status (0.2.0) |
|---|---|
| C1 Film-base-referenced density | ✅ automatic rebate detection, roll base for frames without one, **film-base picker** (`B`) |
| C2 Neutral channel balance | ✅ roll-level dye-gamma ratios, **grey picker** (`N`), **film profile** from a ColorChecker shot on film (crosstalk + slopes + contrast). Automatic balance alone is limited to about ±0.02 in slope |
| C3 Print curve instead of `**(1/1.4)` | ✅ **Auto print** (split grade + paper toe/shoulder, neutral) by default; flat 1:1 master on `L` |
| C4 HOLD | ✅ |
| H1 Colour management | ◐ sRGB ICC in JPEG and TIFF; camera profile from an IT8 transparency. No wide-gamut output, preview not colour-managed |
| H2 Accuracy tests | ✅ 133 tests (accuracy, edge cases, GUI end to end); they run from the sdist and on Python 3.10 |
| H3 UI-thread work | ◐ folder import is parallel (12 × 45 MP previews in 7 s); hot-folder import and flat-field recompute still run on the UI thread |
| H4 RAW formats | ✅ every format LibRaw reads |
| H5 Single source tree | ◐ `smneg_fixed/` is the release candidate; the old `src/` copy must not be published |
| H6 Licences of bundled apps | ✅ NOTICE rewritten; license files shipped in the PyInstaller apps |
| M1 Non-RAW inputs | ✅ JPEG / PNG / 8-bit TIFF linearized as sRGB |
| M3 Preview = export | ✅ statistics from the preview reused at full resolution; sharpness radius scales with size |
| M4 Memory | ◐ 16-bit export of a 45 MP frame: 4.1 s; peak about 5–6 GB with zoom cache (Classic: 5.1 GB) |
| M5 Logging | ✗ still `print` / status bar only |
| M6 B&W mode | ✅ detected automatically (not fooled by a plain sky), rendered neutral |
| Next | validation on real IT8 / ColorChecker scans shot on film; Adobe RGB / ProPhoto export; cast removal in three tone zones; split `window.py`; logging |

## Scorecard

| Area | Score | Reason |
|---|---|---|
| Color accuracy | **3/10** | Greys are wrong in tone (ΔE00 13–16 on synthetic charts), the colour anchor depends on content, there is no film-base reference and no colour management. |
| Code quality | **6/10** | Small, readable modules, SPDX headers, CI, type hints. But `window.py` is 1,683 lines, there is a HOLD bug, heavy work runs on the UI thread, and errors are caught too broadly. |
| Performance | **6/10** | About 8 s per 45 MP frame end to end, with export pipelining. Peak memory is about 5 GB, and import and flat-field run on the UI thread. |
| UX | **6/10** | Fast keyboard workflow with undo and sessions. But the +D direction is reversed, values are hidden, there is no grey/base picker, and only Nikon/Fuji/DNG RAWs are accepted. |
| Docs | **6/10** | Clear structure. But they call the 99.5th percentile the "film base", TIFF decoding is described out of date, and NOTICE says dependencies are "not bundled" when the release apps bundle them. |
| Tests | **5/10** | 86 tests pass. But nothing measures colour accuracy, and the golden test freezes the current (inaccurate) output. |

---

## Phase 1 – The project

### Files

| File | Role |
|---|---|
| `src/smneg/engine.py` (210 lines) | Decoding (`decode_negative`), inversion (`OfficialFilmEngine.load_negative_base`, `_invert_channel`), colour pipeline (`apply_pipeline`), tone profiles (`tone_curve`) |
| `src/smneg/window.py` (1,683) | Main window: UI, keyboard, render orchestration (`render_frame`, `render_frame_16bit`), undo, HOLD/copy-paste, import, hot folder, zoom jobs, session restore, export loop |
| `src/smneg/views.py` (438) | Frame cards, enlarged view, zoomable canvas |
| `src/smneg/export.py` (876) | Export dialog, filename templates, JPEG/TIFF writing (`save_image`, `save_tiff16`), XMP/EXIF, session-info dialog |
| `src/smneg/crop.py` (242) | Manual crop dialog, straighten, crop rotation |
| `src/smneg/flat_field.py` | Flat-field gain map; RAW extension list |
| `src/smneg/session.py` | Session JSON read/write and validation |
| `src/smneg/settings.py` | `QSettings` and legacy migration |
| `src/smneg/hot_folder.py` | Polls a folder for finished files |
| `src/smneg/capture.py` | macOS NX Tether trigger (JXA) |
| `src/smneg/camera_reference.py` | Compares EXIF capture settings between frames |
| `src/smneg/models.py` | `FrameItem` dataclass (per-frame settings and preview base) |
| `src/smneg/zoom.py`, `help.py`, `app.py`, `__main__.py` | "Original" dialog, shortcuts dialog, entry point |
| `tests/` | 86 tests (golden inversion, pipeline, TIFF, crop, sessions, names, GUI workflow, export failure) |
| `packaging/`, `.github/workflows/` | PyInstaller spec, CI (macOS/Windows × py3.10/3.12), release |

### Architecture

```
UI layer (Qt main thread)        window.py ─ views.py ─ crop.py ─ export.py (dialogs) ─ zoom.py ─ help.py
   │  keyboard → FrameItem fields → render_frame()  (runs on the main thread, every key press)
   ▼
Engine (pure NumPy/OpenCV)       engine.decode_negative → flat_field.apply_flat_field → load_negative_base → apply_pipeline
   ▲
Threads                          restore_worker (2) · zoom_worker (1) · export loader (1) + writer (1)
                                 load_negative_base: 3 threads, one per channel, above 4 MP
File I/O                         rawpy/LibRaw · OpenCV (TIFF) · Pillow (JPEG/PNG) → export.save_image (Pillow JPEG / tifffile)
Settings & state                 settings.py (QSettings) · session.py (smneg-session.json) · hot_folder.py
```

### Pipeline, step by step

| # | Step (file → function) | dtype / bits | Range | Encoding |
|---|---|---|---|---|
| 1a | RAW: `engine.decode_negative`, `rawpy.postprocess(output_bps=16, gamma=(1,1), no_auto_bright, user_wb=1, output_color=raw)`; AHD demosaic at full resolution, `half_size` for previews | uint16 → float32 /65535 | 0..1 (Z8 test frame peaked at 0.29) | **Linear camera-native RGB** (no WB, no matrix). Correct for negatives. |
| 1b | Preview resize: per channel, Pillow BILINEAR to 1600 px | float32 | 0..1 | linear |
| 1c | TIFF (`smneg_fixed`): `cv2.imdecode(IMREAD_UNCHANGED)` | uint8/uint16 → float32 | 0..1 | **Assumed linear**; ICC and tags ignored; float TIFF rejected |
| 1c' | TIFF (original `src/`): `PIL.convert("RGB")` | **8-bit** → float32 | 0..1 | assumed linear |
| 1d | JPEG/PNG: Pillow `convert("RGB")` | uint8 → float32 | 0..1 | **sRGB-encoded but treated as linear** |
| 2 | `flat_field.apply_flat_field` (RAW only) | float32 | ~0..1 | linear (the right domain) |
| 3 | `load_negative_base` → `_invert_channel`: `base = P99.5(inner 20–80 %)`; `t = clip(v/base, 1e-4, 1)`; `D = −log10 t`; `out = clip((D − P0.5)/(P99.5 − P0.5), 0, 1)` per channel | float32 | 0..1 | **Normalized log density**, each channel stretched on its own (an auto-levels in log space) |
| 4 | `apply_pipeline`: `x ** (1/1.4)`; C/M/Y gains `2^(−0.04·pts)`; density gain `2^(0.04·steps)`; contrast around 0.5; HSV saturation; mirror/rotate/auto-crop | float32 | clipped 0..1 at every step | Undefined: density values used as **display code values** |
| 5a | Preview/JPEG: `(clip·255).astype(uint8)` (truncates; average −0.5 code) | uint8 | 0..255 | Displayed as if sRGB (Qt `QImage` has no colour space set, so on P3 screens it is shown unmanaged) |
| 5b | TIFF: `output_float=True` → `render_frame_16bit` → `rint(·65535)` | uint16 | 0..65535 | Same, untagged |
| 6 | `window.render_frame`: tone profile (an 8-bit LUT on 8-bit data for previews, so quantized twice), straighten (cubic), sharpness (Gaussian σ = 1 px, **independent of resolution**), crop | as above | | |
| 7 | `export.save_image`: Pillow JPEG (4:4:4 at q≥95, EXIF, **no ICC, no EXIF ColorSpace**); `save_tiff16`: tifffile uint16 deflate + XMP, **no ICC** | 8 / 16 bit | | **Untagged** |

---

## Phase 2 – Color science and image quality

All numbers come from `tests/audit/audit_color.py` (synthetic negative: 24-step reflective grey wedge
D 0.06–2.36, a film model with orange mask, per-layer gammas, toe and shoulder, a camera model with light colour
and crosstalk, and an unexposed rebate) plus one real NEF (`it8_profiler/data/NIG_TEST RAW/NIG_TEST_1.NEF`).
Output is read as sRGB (the files are untagged) and converted to CIELAB D65. The colour results are
**identical** for `src/` and `smneg_fixed/src/`.

### Claim 1: the film base is not used; colour comes from percentiles and drifts – **CONFIRMED** (with one nuance)

Code: `engine.py:102` takes `base = np.percentile(inner, 99.5)`. That is the brightest 0.5 % of the image
(clear shadows), not the rebate. Then `engine.py:110–111` stretches each channel between its own 0.5 and
99.5 percentiles. Because `−log10(v/base) = −log10 v + log10 base`, the base is a constant offset in density,
and the stretch removes any constant offset (and any channel scaling) exactly. Measured (`[5]`):

| Change applied before inversion | Max change of `load_negative_base` output |
|---|---|
| Real rebate base (0.85, 0.39, 0.19) instead of the 99.5th percentile (0.56, 0.25, 0.12) | **1.2e-07** |
| Channels pre-scaled ×(0.5, 1.7, 3.0) (another mask colour or light) | **1.2e-07** |
| Scan 1 EV darker | **0** |

So the orange mask, the light colour and the scan exposure have no effect. The last one is good: scan
exposure *should* not matter. The first two are the problem: colour balance is decided only by the frame's
extremes.

- **Content dependence** (`[4]`, identical small grey wedge, film and camera unchanged, only the rest of the
  scene changes): GS7 comes out as L*a*b* 83/−4.6/+7.3 (balanced), 88/−5.7/−1.9 (warm), 89/−1.1/+4.0 (cool).
  Mean wedge chroma ranges from 1.2 to 10.1. The base-referenced prototype stays at C* 1.5 in all five scenes.
- **Real NEF** (`[7]`): the same pixels rendered from the full frame and from a 60 % crop differ by **ΔE00 3.4**
  (b* +2.8 → +0.1). Changing only the framing changes the colour.
- **Film exposure** (`[3]`, EV −2…+2): GS7 L* goes 76.5 → 83.9 and a* goes −0.2 → +2.5. The drift is real but mostly
  in brightness. Pure *scan* exposure has no effect.
- **Nuance, to be fair:** on a frame that is almost all chart (like an IT8 shot), the wedge itself sets the
  percentiles and SMneg's greys are neutral (C* 0.2 in `[1]`). The colour drift appears in real photographs.
  NegPy also stretches per channel by percentiles; the difference is that it ties the stretch to the film base
  and adds a neutrality constraint across channels (Phase 7).

### Claim 2: no real tone curve – **CONFIRMED**

`engine.py:168` computes `plane = base_positive ** (1/1.4)`, and the result is written as 8/16-bit code values
(`engine.py:202`, `window.py:442`). The value is proportional to *density*, which is the logarithm of scene
luminance, so the image has a log-like tone. Then every viewer decodes it as sRGB as well.

Per-step result (`[1]`, Portra-like, D65, normal exposure):

| | Reference | SMneg default | SMneg, best single density key (−18) | Prototype |
|---|---|---|---|---|
| Grey ΔE00 mean / max | – | **16.0 / 29.7** | 6.0 / 21.8 | **2.0 / 4.0** |
| Mid-grey (GS7–15) ΔL* | 0 | **+28.3** | +5.2 | +1.3 |
| Top 9 steps L* | 44–95 | **73–100** (squeezed) | 46–64 (whites go grey) | 45–94 |
| Bottom 5 steps L* | 4–10 | 0–24 (last step clipped to 0) | 0–14 | 8–13 |
| 16-bit vs 8-bit | – | 16.1 vs 16.0 | | |

Synthetic matrix (`[2]`) next to the Reddit table:

| Roll | SMneg | SMneg best D | Prototype | Reddit SMneg / NegPy |
|---|---|---|---|---|
| Portra-like D65 | 16.0 | 6.0 | 2.0 | 5.8–7.6 / 2.4–2.6 |
| Portra-like LED | 16.0 | 6.0 | 2.6 | 8.8–13.1 / 2.8–3.3 |
| Ektar-like D65 | 13.3 | 4.9 | 2.9 | 12.3 / 7.9 |
| Ektar-like LED | 13.3 | 4.9 | 3.4 | 21.5 / 8.1 |

The absolute numbers differ from Reddit because the film and camera models are synthetic. The pattern is
the same: the error comes from the *shape* of the tone curve, so no density or contrast key setting can fix it.
The best possible density key still leaves ΔE 5–6 and greys out the whites. Note also that `+1D`
makes the picture *brighter* (`engine.py:173`), the opposite of printer-density convention.

The other profiles don't help: "Flat" = `0.12 + 0.76x` (blacks lifted to L* ≈ 13, whites capped at L* ≈ 89),
and "S Curve" adds contrast. None of them is a print curve.

### Claim 3: no colour management – **CONFIRMED**

- Input: `output_color=rawpy.ColorSpace.raw` (`engine.py:30`). Camera-native RGB is never converted to a
  defined space.
- Working space: none is defined; the arithmetic runs on camera RGB with log-density values.
- Output: `save_image` and `save_tiff16` write no ICC profile and no EXIF ColorSpace tag (`export.py:123–197`).
  `grep icc` finds nothing in the code. The preview `QImage` has no colour space set.
- Effect: greys are not affected (a camera matrix maps neutrals to neutrals), but colour patches get the
  camera's primaries interpreted as sRGB. Saturation and hue are wrong in a camera-dependent way.
  (NegPy does not apply the camera matrix for negatives either, but it does work in a defined space,
  Adobe RGB, and converts at output.)

### Claim 4: 16-bit TIFF truncated to 8-bit – **CONFIRMED in the original `src/` (v0.1.0), FIXED in `smneg_fixed`**

Test: a 16-bit TIFF with values 10000 and 10001. The original `src/` decodes both to `0.15294118` (one value,
8-bit). `smneg_fixed` keeps two distinct values. RAW was always 16-bit. Internal processing is float32
throughout, and TIFF export is 16-bit. Previews and JPEG are 8-bit, as expected.
**If GitHub still holds the original `src/`, the published version has this bug.**

### Claim 5: linear RAW treated as gamma-encoded – **FALSE for RAW, PARTLY TRUE elsewhere**

- RAW: `gamma=(1,1)` and `no_auto_bright`, followed by `−log10` of transmittance. This is correct linear handling.
- JPEG/PNG/8-bit TIFF (sRGB-encoded) and gamma-encoded scanner TIFFs are assumed linear. Measured: a
  value that is linear 0.18 enters the engine as 0.463, and the log slope is 0.46 instead of 1. The per-channel
  stretch absorbs most of this, but shadows are distorted and the result is undefined.
- The real encoding mix-up is on the **output** side: log-density values are written as if they were display
  (sRGB) values (claim 2).

### Claim 6: README / docs promises – see Phase 6

The README does **not** claim ICC management or float32. Its inaccurate claims are listed in Phase 6.

### Test harness

```bash
python tests/audit/audit_color.py                         # synthetic grey wedge, sections [1]–[6]
python tests/audit/audit_color.py --nef PATH.NEF          # + real-negative content test [7]
python tests/audit/audit_color.py --src ../src            # audit another copy
python tests/audit/audit_perf.py PATH_TO_45MP.NEF         # timings, memory, preview vs export
```

For each step it reports L*, a*, b*, ΔE2000 against the reference, and the neutrality (C*) of the grey ramp.
It drives the unmodified engine by substituting `decode_negative` (the same approach as the golden test).
The files are named `audit_*.py`, so pytest does not collect them. To measure real IT8 negatives, add patch
sampling on the rendered output (the corner/patch layout code in `it8_profiler/camera_profile/profiler.py`
can be reused). I need IT8.7/2 negative scans and the target's reference file for that (see Summary).

---

## Phase 3 – Code quality and bugs

| Sev. | Finding | Where | Evidence |
|---|---|---|---|
| **High** | **HOLD discards edits**: `adjust_color`/`adjust_density` call `apply_hold_if_active()`, which writes the *old* held snapshot back. With HOLD on, Q/W/E/↑/↓ do nothing, yet an undo step is recorded. | `window.py:1218, 1236, 1329` | Offscreen run: cyan 3 → +C → **3** (expected 4); density 0 → +5 → **0** |
| **High** | Turning HOLD on overwrites the settings (including rotation) of **every later frame**, with no undo for those frames. | `window.py:1321, 1332` | Code reading |
| High | Only `.raf .nef .nrw .dng` count as RAW. Canon (CR2/CR3), Sony (ARW), Olympus, Panasonic and Pentax files are not even listed in the import dialog. | `flat_field.py:7`, `window.py:47` | – |
| High | The colour engine issues from Phase 2. | `engine.py` | – |
| Medium | Import (`select_roll_folder`), hot-folder import, flat-field recompute (`set_flat_field`) and export rendering run on the **UI thread**. A 45 MP preview decode takes about 1.1 s per frame, so a 36-frame roll takes about 40 s with a modal dialog, and hot-folder imports freeze the UI. | `window.py:1099, 1028, 578, 1503` | perf run |
| Medium | `load_negative_base` catches `Exception` (including `MemoryError`), prints it, and returns `None`. There is no logging module; `print` output is invisible in the packaged app. | `engine.py:148` | – |
| Medium | Sharpness uses σ = 1 px at every resolution, so the preview shows about 1.7× more sharpening than the export. | `window.py:321, 438` | Laplacian gain: preview ×1.91, export ×1.12 |
| Medium | Preview and export differ (half-size demosaic, percentiles recomputed): ΔE00 mean 1.8, p95 3.7, max 21. | – | `audit_perf.py` |
| Medium | B&W negatives: no monochrome mode. Each channel is stretched separately, so stain or light colour can tint the result. Output is always RGB. | – | – |
| Low | `astype(uint8)` truncates instead of rounding (average −0.5 code). For previews, the tone profile LUT is applied to already-quantized 8-bit data. | `engine.py:202`, `window.py:314` | – |
| Low | Contrast pivots at display value 0.5 and clips. Saturation in HSV changes luminance. | `engine.py:180–186` | – |
| Low | Leftover French strings ("indisponible", "TIFF write failed :") and French section comments. | `window.py:541, 717, 854`; `export.py:155` | – |
| Low | `OfficialFilmEngine.errors` is a class-level dict shared across threads. It is safe under the GIL but grows without limit. | `engine.py:96` | – |
| Low | Copy/paste and HOLD don't include `straighten` or `manual_crop`. The clipping toggle has no undo (probably intended). | `window.py:1347` | – |
| Info | Two diverging copies (`src/` and `smneg_fixed/src/`) with no git history. High risk of shipping the wrong one. | – | – |

Dead code and unused settings: none of significance (pyflakes is not installed here; `FIXES.md` reports
it clean). The `base` value in `_invert_channel` has no effect on the result (claim 1), so it is effectively dead.

Threading: no data races found. The zoom job copies the `FrameItem`, and the export threads touch only
their own arrays. Memory: each frame keeps a float32 preview base (about 20 MB at 1600×1066), so 36 frames use
about 0.7 GB. The zoom cache holds one full-resolution base (548 MB). An export holds up to about 3 full frames at once.

---

## Phase 4 – Performance (Nikon Z8 NEF, 8280×5520, Apple M1 Max, `audit_perf.py`)

| Stage | Time | Peak RSS |
|---|---|---|
| `decode_negative` full (LibRaw AHD) | 2.53 s | 1.85 GB |
| `load_negative_base` (inversion) | 0.87 s | **4.08 GB** |
| `apply_pipeline` → uint8 | 1.35 s | 5.12 GB |
| `apply_pipeline` float → uint16 | 1.69 s | 5.12 GB |
| TIFF 16-bit write (deflate 1) | 1.28 s | – |
| JPEG q100 write | 0.57 s | – |
| Preview decode + invert (half-size) | 1.14 s | – |

That is about 7–8 s per exported frame; export overlaps load and write, so throughput is roughly 4–5 s per frame.
The memory peaks come from float32 copies made at every step (values, result, three channel planes,
percentile copies, `np.power` and clip temporaries). The slowest parts are demosaicing (LibRaw) and the
element-wise power and clip passes in `apply_pipeline`. Both can be cut a lot (in-place ops, a 1D LUT for
the tone curve, percentiles on a subsample).

---

## Phase 5 – UX

What works: a keyboard-first, Frontier-like workflow, a 6-frame grid, undo/redo, sessions with metadata,
hot folder, flat field, clipping view, and a clear export dialog.

What confuses or is missing:
- **+D brightens.** In printer-lights language more density means a darker print. Choose one convention and label it ("Exposure +" or "Density +").
- **Values are hidden.** The info bar shows contrast, saturation and sharpness, but not C/M/Y/D. A photographer needs to see "C+3 M−1 Y+2 D−4" all the time.
- **HOLD** is broken (Phase 3) and destructive.
- **No neutral picker.** The most useful tool after inversion is "click a grey/white/black point" (or "click the film rebate"). That is a precise, non-auto correction that keeps your no-auto-enhancement rule.
- **No roll-level base or colour:** you can't sample the base once per roll and apply it to all frames (this is how a lab works and how drift is avoided).
- **No before/after toggle** on the corrected image, and no numeric readout under the cursor (RGB / L*a*b* / density).
- **Tone profiles** "Natural / Flat / S Curve" are not what their names suggest (Phase 2).
- Error messages from failed decodes appear only in the status bar or in `print`.

What a photographer needs most after inversion: (1) a correct, base-anchored neutral starting point so you rarely need corrections, (2) a one-click grey/rebate picker, (3) visible CMY/D numbers with printer-point steps, (4) roll-wide apply.

---

## Phase 6 – Open-source readiness

### README and docs compared with the code

| Claim | Reality |
|---|---|
| "Density-based negative inversion engine" | Density is computed, but the base cancels out and the output *is* density used as display values (no print step). |
| how-it-works §3 "Film base level: 99.5th percentile" | That is the clearest image area, not the film base, and it has no effect on the result. |
| how-it-works §1 "the orange mask … is kept" | It is kept at decode and then removed by the per-channel stretch, not through a measured base. |
| how-it-works §1 "TIFF and JPEG are read with Pillow" | `smneg_fixed` reads TIFF with OpenCV. |
| how-it-works §3 "bit-identical … a test checks it" | The test uses tolerances (`rtol=1e-5`). |
| "export … with proper metadata" | No colour-space metadata (no ICC, no EXIF ColorSpace). |
| "RAW (`.raf .nef .nrw .dng`)" | Accurate, but this means most camera brands are unsupported. |
| "Windows: expected to work" | Honest. Never tested on real hardware. |
| NOTICE "installed separately, not bundled" | **Wrong for the .dmg/.zip releases**: PyInstaller bundles Qt/PySide6 (LGPL-3.0), LibRaw (LGPL-2.1/CDDL) and OpenCV. Their licence texts must ship with the apps, and LGPL replaceability should be documented. |
| "tested with … OpenCV 5.0" | Not verifiable here (this machine has 4.10). |
| Not claimed: float32, ICC | Correct, not claimed. |

### Tests
86 tests pass in `smneg_fixed` (44 in the original). Covered: inversion golden, pipeline basics, TIFF precision,
crop/rotation, sessions, names, settings, hot folder, export failure, a GUI smoke test.
**Missing:** any colour-accuracy or neutrality test, preview-vs-export consistency, RAW decoding (no RAW
fixture), HOLD and copy/paste behaviour. **Important:** `test_engine_golden.py` freezes the current output,
so it will (correctly) fail when the engine is fixed. Replace it with accuracy tests based on `audit_color.py`.

### Packaging
pyproject is fine (setuptools, an `[tiff]` extra, an entry point). Dependency floors are unpinned, and there is no
lock file for the release builds. The version is duplicated in three places. CI builds the wheel, sdist and native
apps, but it does not test RAW decoding or the frozen apps. macOS and Windows differ only in the capture button
and key labels.

### Licence and images
Every `.py` has an SPDX Apache-2.0 header. The photo rights are stated in the README. Recommendation: add a
`docs/images/LICENSE` (or a REUSE `.reuse/dep5`) so the "all rights reserved" status sits next to the files, and
make sure the sdist doesn't pick up the images without that notice. Because NegPy is GPL-3.0, **don't copy its
code** into this Apache-2.0 project; reusing its concepts is fine.

---

## Phase 7 – How NegPy does it (from its `docs/PIPELINE.md`, GPL-3.0)

In plain words:

| Topic | NegPy | SMneg |
|---|---|---|
| Decode | Linear RAW, camera RGB, unity WB (same as SMneg) | Same |
| Working space | Defined: Adobe RGB (1998), D65. Lab is computed from linear data. | None |
| Film base | Read from the **rebate** (flat 8-px blocks) or picked by hand. Densities are measured *above the clear base*. | 99.5th percentile, cancelled out |
| Density domain | `log10` of the scan, per-channel bounds from very wide percentiles (0.01–99.99 %), **plus a shared luma "reach" term that keeps a grey scale neutral when channels have different ranges** | Narrow percentiles (0.5–99.5 %), fully independent channels |
| Tone | A real **print curve**: density mapped through an H&D paper curve (straight line plus soft toe and shoulder, Dmin 0.06, Dmax 2.3, grade in ISO-R), then `10^−D` gives linear print light | `density ** (1/1.4)` written as display values |
| Exposure/contrast | Auto Density and Auto Grade meter towards fixed targets with *partial* pulls and clamps (optional) | Fixed by the percentiles |
| Output | Scene-linear until the end, then an Adobe RGB transfer curve; ICC conversion at export; monitor profile and soft proofing | Untagged |
| Precision | float32 engine, 16-bit TIFF or lossless JXL export, GPU and CPU paths identical | float32 engine, 16-bit TIFF |

**What SMneg should learn:** (1) anchor everything to the measured film base; (2) when you stretch per channel,
constrain the channels so greys stay grey; (3) turn density into *print light* with a paper-like curve
instead of showing density; (4) work in one defined colour space and tag the output.

---

## Phase 8 – Fix roadmap

Targets come from `tests/audit/audit_color.py`, and from real IT8 negatives once you provide them.
"Flat/neutral" will be defined as: **grey ΔE00 mean ≤ 3 (Portra, D65), C* mean ≤ 1.5, content drift ΔE ≤ 1, EV ±2 drift ΔL* ≤ 3**.

### Critical

| # | Item | Why it matters to the photo | Files | Risk / effort | Measure |
|---|---|---|---|---|---|
| C1 | **Film-base-referenced density**: sample the rebate (auto-detect plus manual "click the base"), per channel; store it per roll; `D = −log10(v / base)` | Colour stops depending on framing and content; frames on one roll match | `engine.py` (new `film_base.py`), `window.py` (picker, roll setting), `models.py`, `session.py` | Med / M. **This changes `load_negative_base`, so it needs your approval.** | `[4]` content drift C* ≤ 1.5 in all scenes; real NEF crop test ΔE ≤ 1 |
| C2 | **Neutral channel balance in density space**: per-channel slope from a stock profile *or* a shared-range constraint (like NegPy's luma reach), never independent endpoints. Optional one-click grey or rebate neutral. | Greys stay grey without auto-enhancement | `engine.py` | Med / M | wedge C* mean ≤ 1.5 at EV −2…+2 |
| C3 | **Print curve instead of `**(1/1.4)`**: density → scene log exposure → a documented neutral print curve (straight section of slope 1 for "flat", soft toe and shoulder only to avoid clipping) → linear light → working-space encoding | Mid-greys at the right L*, open highlights, shadows not crushed. This is the biggest ΔE gain. | `engine.py` (`apply_pipeline`, `tone_curve`), `window.py` | Med / M | grey ΔE00 mean ≤ 3 (synthetic and Portra D65 IT8), mid-grey ΔL* ≤ 2 |
| C4 | **Fix HOLD** ✅ *done 2026-11-10*: edits on the current frame are no longer reverted. Turning HOLD on copies the settings to the following frames as **one undoable step** (the current frame is left alone). | Your edits work again | `window.py` | Low / S | 3 new GUI tests in `tests/test_gui_workflow.py`; 89 pass |

### High

| # | Item | Why | Files | Risk / effort | Measure |
|---|---|---|---|---|---|
| H1 | **Colour management**: working space (linear Rec.2020 or Adobe RGB); a camera matrix (LibRaw `rgb_xyz_matrix`, or an IT8 profile from your `it8_profiler`) for transparencies and as an option; embed an ICC profile (sRGB for JPEG, Adobe RGB or ProPhoto for TIFF) via Pillow `icc_profile=` and the tifffile tag 34675; set the `QImage` colour space | Colours look the same in Lightroom, on the web and in print | `engine.py`, `export.py`, `views.py` | Med / M | exiftool shows the profile; colour-patch ΔE on the IT8 negative ≤ 6 |
| H2 | Replace the golden test with **accuracy tests** (grey ΔE, neutrality, content and EV drift, preview vs export) | Locks in correct behaviour | `tests/` | Low / S | CI fails if grey ΔE > 3 |
| H3 | **Move import, flat-field and export rendering off the UI thread** | No freezes on a 36-frame roll | `window.py` | Med / M | UI stays responsive (no event-loop gap over 200 ms) |
| H4 | Accept all LibRaw RAW formats (CR2, CR3, ARW, ORF, RW2, PEF, 3FR, IIQ…) | Canon and Sony users can use the app | `flat_field.py`, `window.py` | Low / S | Import a sample of each |
| H5 | Single source tree under git; delete or merge the stale `src/` copy; publish the TIFF fix | Avoid shipping the 8-bit TIFF bug | repo | Low / S | `diff` is empty; tag a release |
| H6 | NOTICE and licence bundle for the packaged apps (Qt/PySide6 LGPL, LibRaw, OpenCV) | Licence compliance | `NOTICE`, `packaging/` | Low / S | Licences present inside the .app/.zip |

### Medium

| # | Item | Files | Effort | Measure |
|---|---|---|---|---|
| M1 | Non-RAW inputs: linearise sRGB/gamma TIFF/JPEG (read the ICC or assume sRGB), and accept float TIFF | `engine.py` | S | ramp test: 0.18 enters as 0.18 |
| M2 | Show C/M/Y/D values; fix the +D convention; printer-point steps; grey/rebate picker; before/after; pixel readout | `window.py`, `views.py` | M | user test |
| M3 | Resolution-aware sharpness (σ scaled by output/preview size) and the same inversion statistics for preview and export (compute the base and balance once, from the preview, and reuse them at full resolution) | `window.py`, `engine.py` | S | preview vs export ΔE p95 ≤ 1 |
| M4 | Memory: in-place ops, a LUT for the curve, percentiles on a subsample | `engine.py` | S | peak RSS ≤ 2.5 GB on 45 MP |
| M5 | Real logging (`logging` to a file), with narrower `except` clauses | all | S | log file contains decode errors |
| M6 | B&W mode (single channel, neutral output, optional grayscale TIFF) | `engine.py`, `export.py` | S | B&W wedge C* = 0 |

### Low
- Split `window.py` (import/session, export orchestration, keyboard controller).
- Round instead of truncating to 8-bit; apply tone in float before quantizing.
- Translate the remaining French strings and comments; keep the version in a single source.
- Pin dependency versions for release builds; add a RAW fixture to CI; smoke-test the frozen apps.

### Suggested order
C4 (a small, safe fix now) → **C1 + C2 + C3 together, as one new engine behind a switch ("Engine v2"),
with the old engine kept for comparison** → H2 → H1 → the rest. Before any engine change: send the IT8
negative scans so the targets above are measured on real film, not only on the synthetic model.

### Limits of this audit
- The film and camera model is synthetic. It reproduces the *mechanisms* behind the Reddit results, not the exact numbers.
- The prototype uses the film gammas from the synthetic stock (in practice that means a stock preset or a
  neutrality constraint) and a grey-card click for exposure. It shows the approach is achievable; it is not a finished design.
- Not tested: real IT8 negatives, Windows, frozen apps, other camera brands, RAWs with non-Nikon CFA layouts.
