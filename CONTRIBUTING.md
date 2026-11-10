# Contributing

Thanks for helping! SMneg is a small PySide6 application for photographers who scan film with a digital camera.

## Ways to help
- **Try it and report what happens**, especially on Windows and with RAW files from other cameras
  ([bug report](https://github.com/saidmrigua/SmNeg/issues/new?template=bug_report.yml)).
- **Suggest improvements** ([feature request](https://github.com/saidmrigua/SmNeg/issues/new?template=feature_request.yml)).
- **Improve the docs** in `docs/`: they are plain Markdown.
- **Fix a bug or add a feature**: open an issue first for anything bigger than a small fix, so we agree on the approach.

## Set up
```bash
git clone https://github.com/saidmrigua/SmNeg.git && cd SmNeg
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[tiff,dev]"
QT_QPA_PLATFORM=offscreen pytest -q
python -m pyflakes src tests
```
More detail (layout, tests, how to add a shortcut or preset): [docs/development.md](docs/development.md).

## Ground rules
- **Do not change the inversion math** in `engine.py` (`OfficialFilmEngine.load_negative_base`) without discussion.
  `tests/test_engine_golden.py` compares its output with reference results; it must keep passing.
- Keep changes small and focused; add or update a test when you fix a bug.
- UI text, comments and docs are in English.
- No network calls or telemetry.
- Add a line under *Unreleased* in [CHANGELOG.md](CHANGELOG.md) for user-visible changes.

## Pull requests
Fork, create a branch, push, and open a pull request against `smneg-release`. CI (macOS + Windows) must pass.
By contributing you agree that your contribution is licensed under the Apache License 2.0 (the same as the project),
and you confirm you have the right to submit it. Please do not add photographs to the repository without
permission from their owner.

Be kind: see the [code of conduct](CODE_OF_CONDUCT.md).
