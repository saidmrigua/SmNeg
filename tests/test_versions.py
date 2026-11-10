# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
"""The version number is written in several files; they must agree."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def find(path, pattern):
    match = re.search(pattern, (ROOT / path).read_text(encoding="utf-8"), re.MULTILINE)
    assert match, f"no version found in {path}"
    return match.group(1)


def test_versions_agree():
    versions = {
        "pyproject.toml": find("pyproject.toml", r'^version = "([^"]+)"'),
        "src/smneg/__init__.py": find("src/smneg/__init__.py", r'^__version__ = "([^"]+)"'),
        "packaging/smneg.spec": find("packaging/smneg.spec", r'^version = "([^"]+)"'),
        "CITATION.cff": find("CITATION.cff", r'^version: (\S+)'),
    }
    assert len(set(versions.values())) == 1, versions


def test_changelog_mentions_the_version():
    version = find("pyproject.toml", r'^version = "([^"]+)"')
    assert f"## [{version}]" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
