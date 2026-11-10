<!-- SPDX-License-Identifier: Apache-2.0 | Copyright 2026 Said Mrigua -->
# Using SMneg: a typical scan session

1. **Prepare the scan.** Photograph each negative on a light source with a digital camera (RAW). Keep the
   exposure to the right without clipping any channel. Optionally photograph the bare light source once for
   the flat-field reference.
2. **New Session.** Click `NEW SESSION`, fill in the shoot information (title, client, film, location,
   photographer, copyright) and choose where sessions are stored. Use `SESSION INFO` later to edit it.
3. **Film base (recommended for 35 mm).** Before scanning the roll, photograph the clear film of the leader
   two or three times with the same camera exposure, then `FILM` → *Film base reference…* after the import.
   Without it SMneg reads the base on the rebate between frames, or estimates it.
4. **Import.** Use `Select Roll Folder` to load a folder of scans, or `HOT FOLDER` to import files as they
   arrive from the camera software.
5. **Flat field (optional).** Click `FLAT FIELD` and choose the reference RAW.
6. **Adjust each frame.** `Space` opens the enlarged view. Use `Q/A`, `W/S`, `E/D` for cyan, magenta and
   yellow, `↑/↓` for density, `⌥↑/⌥↓` for contrast, `T` for the tone profile, `K` for a manual crop,
   `Z` to zoom to 100 %. `⌘Z` undoes. With the Scientific engine, `N` then a click on a neutral grey sets
   the color, and `B` then a click on the clear film between frames sets the film base for the roll. `H` keeps the current settings for the next frames.
7. **Mark rejects.** Press `P` to skip a frame at export.
8. **Export.** `⌘E` opens the export dialog: destination, preset (JPEG or 16-bit TIFF), filename template with
   clickable variables, and which photos to include. The session information is already filled in.

See [shortcuts.md](shortcuts.md) for every key and [how-it-works.md](how-it-works.md) for the algorithm.
