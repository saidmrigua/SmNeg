# Third-party software

SMneg's own code is licensed under the [Apache License 2.0](LICENSE). It depends on the open-source
packages below. They are **not modified** by SMneg and keep their own licenses.

| Package | Used for | License |
|---|---|---|
| [PySide6 / Qt for Python](https://doc.qt.io/qtforpython-6/) (Qt 6) | user interface | LGPL-3.0 (also GPL-2.0/3.0 or commercial from The Qt Company) |
| [rawpy](https://github.com/letmaik/rawpy) | RAW decoding binding | MIT |
| [LibRaw](https://www.libraw.org/) (inside rawpy) | RAW decoding | LGPL-2.1 or CDDL-1.0 |
| [opencv-python](https://github.com/opencv/opencv-python) | image operations | Apache-2.0 (bundled OpenCV libraries: Apache-2.0, plus third-party notices shipped in the wheel) |
| [NumPy](https://numpy.org/) | array math | BSD-3-Clause |
| [Pillow](https://python-pillow.org/) | TIFF/JPEG/PNG I/O, JPEG export | HPND |
| [tifffile](https://github.com/cgohlke/tifffile) (optional) | 16-bit TIFF with XMP | BSD-3-Clause |
| [PyInstaller](https://pyinstaller.org/) (build only) | packaging the apps | GPL-2.0 with an exception that allows distributing the built apps under any license |

## Source install (`pip install smneg`)
Packages are installed from PyPI by pip into your own environment, under their own licenses.

## Pre-built apps (`.dmg`, `.zip`)
The apps attached to a GitHub Release are built with PyInstaller and **do contain** the libraries above
(Qt, LibRaw, OpenCV, NumPy, Pillow and their dependencies, plus a Python interpreter).

- The apps are built in *one-folder* mode: Qt and LibRaw stay separate shared libraries inside the app
  (not linked into the executable), unmodified.
- The exact package versions inside each app are the ones `pip` resolved when the Release was built; the
  log of the *Release* workflow in GitHub Actions lists them.
- Full license texts are available from the project links in the table above. Qt for Python's
  LGPL-3.0 text: https://www.gnu.org/licenses/lgpl-3.0.html, source code:
  https://download.qt.io/official_releases/QtForPython/.

This file is an information notice, not legal advice. If you redistribute a modified build, check the
license of each package.
