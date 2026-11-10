<!-- SPDX-License-Identifier: Apache-2.0 | Copyright 2026 Said Mrigua -->
# Releasing a new version

Releases are built by GitHub Actions (`.github/workflows/release.yml`) when a tag `vX.Y.Z` is pushed.

## What the workflow does
1. **validate**: `pyflakes` and `pytest` on macOS and Windows for the tagged revision, and a check that the tag equals the
   package version. Nothing is built or published if this fails.
2. **python-package**: wheel and sdist (`twine check`).
3. **macos-app** (Apple Silicon runner, so the app is arm64 only) and **windows-app**: PyInstaller bundles. Each bundle runs
   `SMneg --self-test` (imports every module, finds the assets, decodes and inverts a sample TIFF, builds the main window
   offscreen) before it is packaged.
4. **publish**: attaches `SMneg-macOS-arm64.dmg`, `SMneg-Windows-x64.zip`, the wheel and the sdist to the Release.

CI (`ci.yml`) additionally installs the built wheel and sdist into a clean virtual environment outside the checkout.

## Checklist
1. Pick the version (semantic versioning): `MAJOR.MINOR.PATCH`.
2. Update it in **four** places: `pyproject.toml`, `src/smneg/__init__.py`, `packaging/smneg.spec` and `CITATION.cff`
   (`tests/test_versions.py` fails if they disagree), and move the *Unreleased* section of [CHANGELOG.md](../CHANGELOG.md)
   under the new version with the date.
3. Run `pytest` and `python -m pyflakes src tests packaging`; test the app by hand with a real roll (see
   [development.md](development.md)).
4. Commit and push to the default branch; wait for **CI** to pass on macOS and Windows.
5. Optional rehearsal: GitHub → Actions → *Release* → *Run workflow* builds and smoke-tests everything without publishing.
6. Tag and push **from a terminal** (the tag must be `v` + the version):
   ```bash
   git checkout smneg-release && git pull
   git tag -a vX.Y.Z -m "SMneg X.Y.Z"
   git push origin vX.Y.Z
   ```
   Creating the tag in the GitHub web form works too, but you must click *Create new tag: vX.Y.Z on publish*;
   typing the name is not enough.
7. Check that all four files are attached to the Release, then download the `.dmg` / `.zip` and open them on a clean machine
   if you can. They are not signed (see below).

## Refreshing the first release while it is being finalized
The maintainer explicitly chose to keep version `0.1.0` during initial validation.
Run the Release workflow on `smneg-release` and enable **Refresh existing first release**.
The workflow validates and builds that exact commit before publication. It backs up
all previous release assets as a workflow artifact (90-day retention), preserves
the old tag as `archive/v0.1.0-<old-object-sha>`, and moves `v0.1.0` using a Git lease.
This updates the automatic source archives too. It replaces the existing downloads,
provides the old app filenames as identical compatibility aliases, and publishes
`BUILD_INFO.txt` and `SHA256SUMS.txt`. All packages retain version `0.1.0`.
After finalization, normal updates should use a new version. An unchecked manual
run remains a build rehearsal and does not publish anything.

## Creator and licenses
SMneg was created and developed by **Said Mrigua**, Copyright 2026 Said Mrigua.
The project's code stays Apache-2.0. Preserve LICENSE and NOTICE, and retain the
independent licenses and attribution of third-party libraries. Native bundles
include these notices in `smneg/licenses`; the frozen self-test checks them.

## Signing (not done yet)
- macOS: needs an Apple Developer ID certificate and notarization (`codesign` + `notarytool`); then users no longer see
  the *unidentified developer* warning.
- Windows: needs a code-signing certificate for SmartScreen reputation.
- PyPI: the project publishes a wheel and an sdist on GitHub only. Publishing to PyPI (`twine upload dist/*`) needs a
  PyPI account and a free `smneg` project name; check availability first.
