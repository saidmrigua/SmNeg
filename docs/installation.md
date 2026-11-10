<!-- SPDX-License-Identifier: Apache-2.0 | Copyright 2026 Said Mrigua -->
# Installation

SMneg runs on macOS (developed and used there) and Windows (see [troubleshooting](troubleshooting.md#windows)).
Requirements for a source install: Python 3.10 or newer, about 1 GB of disk for the dependencies, and several GB
of RAM for 45 MP class frames.

## Pre-built app (easiest)
Download the file for your system from the [latest Release](https://github.com/saidmrigua/SmNeg/releases/latest).
The apps are **not code-signed or notarized**, so the system asks for confirmation the first time.

| System | File | Notes |
|---|---|---|
| macOS 11+ on Apple Silicon (M1 or newer) | `SMneg-macOS-arm64.dmg` | Intel Macs: [install from source](#from-source) |
| Windows 10/11, 64-bit | `SMneg-Windows-x64.zip` | the interface has not been checked on real Windows hardware yet |

The refreshed `v0.1.0` also provides `SMneg-macOS.dmg` and `SMneg-Windows.zip` as compatibility aliases of the same corrected builds. See `BUILD_INFO.txt` for the source commit and `SHA256SUMS.txt` for file checksums.

### macOS (Apple Silicon): `SMneg-macOS-arm64.dmg`
1. Open the `.dmg` and drag **SMneg** to *Applications*.
2. Open it. macOS will refuse because the app is from an unidentified developer.
   - macOS 14 and older: right-click the app → *Open* → *Open*.
   - macOS 15 and newer: open **System Settings → Privacy & Security**, scroll down to the message about SMneg
     and click **Open Anyway**.
   - Alternative in Terminal: `xattr -dr com.apple.quarantine /Applications/SMneg.app`
3. The optional *CAPTURE* button (Nikon NX Tether trigger) needs **System Settings → Privacy & Security →
   Accessibility** permission for SMneg.

### Windows: `SMneg-Windows-x64.zip`
1. Unzip the folder anywhere and run `SMneg.exe` inside it (keep the other files next to it).
2. If SmartScreen warns, choose *More info → Run anyway*.
3. The capture button is disabled on Windows.

## From source
```bash
git clone https://github.com/saidmrigua/SmNeg.git smneg && cd smneg
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[tiff]"        # "tiff" adds XMP metadata in 16-bit TIFF
smneg                           # or: python -m smneg   or: python smneg.py
```
Or install the wheel from a Release: `pip install smneg-0.1.0-py3-none-any.whl`.

## Uninstall and reset
- Delete the app (or `pip uninstall smneg`).
- Settings live in Qt's `QSettings` under the name *SMneg*: a property list file in `~/Library/Preferences` on
  macOS (search that folder for "SMneg"), the registry key `HKEY_CURRENT_USER\Software\SMneg` on Windows. Delete
  it to reset the app.
- Session data is in the session folders you created (`smneg-session.json`); SMneg does not delete them.
