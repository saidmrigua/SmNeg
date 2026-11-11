# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
# PyInstaller spec:  pyinstaller packaging/smneg.spec --noconfirm
import sys
from pathlib import Path

root = Path(SPECPATH).parent
assets = root / "src" / "smneg" / "assets"
icon = str(assets / ("icon.icns" if sys.platform == "darwin" else "icon.ico"))
version = "0.2.0"
version_numbers = tuple(int(part) for part in (version.split(".") + ["0"] * 4)[:4])   # Windows file version

analysis = Analysis(
    [str(root / "packaging" / "launcher.py")],
    pathex=[str(root / "src")],
    datas=[(str(assets), "smneg/assets")] + [
        (str(root / name), "smneg/licenses")
        for name in ("LICENSE", "NOTICE", "THIRD_PARTY_LICENSES.md")
    ],
    excludes=["tkinter"],
)
pyz = PYZ(analysis.pure)
version_info = None
if sys.platform == "win32":
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo, StringFileInfo, StringStruct, StringTable,
        VarFileInfo, VarStruct, VSVersionInfo,
    )
    version_info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=version_numbers, prodvers=version_numbers,
                          mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
        kids=[StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", "Said Mrigua"),
            StringStruct("FileDescription", "SMneg — Film Negative Inversion"),
            StringStruct("FileVersion", version),
            StringStruct("ProductName", "SMneg"),
            StringStruct("ProductVersion", version),
            StringStruct("LegalCopyright", "Copyright 2026 Said Mrigua"),
            StringStruct("OriginalFilename", "SMneg.exe"),
        ])]), VarFileInfo([VarStruct("Translation", [1033, 1200])])],
    )
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name="SMneg", console=False, icon=icon, version=version_info)
collected = COLLECT(exe, analysis.binaries, analysis.datas, name="SMneg")
if sys.platform == "darwin":
    app = BUNDLE(
        collected, name="SMneg.app", icon=icon, bundle_identifier="com.saidmrigua.smneg",
        info_plist={
            "CFBundleShortVersionString": version,
            "CFBundleVersion": version,
            "NSHighResolutionCapable": True,
            "NSHumanReadableCopyright": "Copyright 2026 Said Mrigua",
        },
    )
