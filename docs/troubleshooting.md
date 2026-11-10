<!-- SPDX-License-Identifier: Apache-2.0 | Copyright 2026 Said Mrigua -->
# Troubleshooting

## The app does not open
- **macOS says the app "cannot be opened" / "is damaged"**: it is not notarized. See
  [installation](installation.md#macos-apple-silicon-smneg-macos-arm64dmg) (*Open Anyway*, or `xattr -dr com.apple.quarantine`).
- **Windows SmartScreen blocks it**: *More info → Run anyway*.
- **From source: `ModuleNotFoundError`**: activate the virtual environment and run `pip install -e ".[tiff]"`.
- **From source on Linux or a server**: Qt needs a display. For tests use `QT_QPA_PLATFORM=offscreen`.
- Run `python -m smneg` from a terminal to see the error message.

## Colors look wrong
- The orange mask is removed by the density inversion; a strong color cast on one frame is normal. Use
  `Q/A`, `W/S`, `E/D` to correct it, then `H` (Hold) to keep the setting for the next frames.
- Keep the **bare light source** exposure to the right without clipping any channel when you scan. Clipped channels
  cannot be recovered.
- Uneven corners: shoot the bare light source once and use *FLAT FIELD*. SMneg rejects a reference that is
  over-exposed, too dark, or framed differently from the scan.
- Press `O` to compare with the original (before inversion).

## Slow or out of memory
- 45 MP class frames need several GB of RAM at 100 % zoom (the last full-resolution frame is cached).
- RAW decoding speed is limited by LibRaw; previews use a half-size decode. Export decodes at full resolution.
- Close other heavy apps and export in smaller batches if memory is tight.

## Export
- **"Choose the destination folder" stays red**: pick a folder you can write to.
- **TIFF has no XMP metadata**: install `tifffile` (`pip install tifffile`, or `pip install "smneg[tiff]"`).
- **A frame is missing**: it was marked **PASS** (`P`). Press `P` again to restore it.
- **"not exported ... could not be decoded at full resolution"**: the source file is missing, moved or damaged. Fix the
  file and export that frame again; the other frames were exported normally.
- **"Invalid session file"**: the `smneg-session.json` is damaged or was edited by hand. Restore it from a backup or delete
  it (your images are not touched; frame settings stored in it are lost).
- **Names have no city / location**: empty variables are dropped on purpose with their separator.

## Capture button (Nikon NX Tether)
Only on macOS, and only for NX Tether. Grant SMneg the **Accessibility** permission (System Settings → Privacy &
Security → Accessibility). The button is disabled on Windows.

## Windows
SMneg is developed on macOS. The non-GUI tests run on Windows in CI, but the interface has not been checked on real
Windows hardware yet. Reports are welcome: open an [issue](https://github.com/saidmrigua/SmNeg/issues/new/choose).

## Still stuck?
Open an issue with: SMneg version (`F1`, bottom line), operating system, camera/RAW format, what you did, what you
expected, and the terminal output if any. Please do not attach client photos you are not allowed to share.
