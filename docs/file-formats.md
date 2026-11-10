<!-- SPDX-License-Identifier: Apache-2.0 | Copyright 2026 Said Mrigua -->
# Files in and out

## Input
| Type | Extensions | Notes |
|---|---|---|
| RAW | every format LibRaw reads (`.nef .raf .dng .cr2 .cr3 .arw .orf .rw2 .pef` …) | decoded as linear data, no white balance (see [how it works](how-it-works.md)) |
| Raster | `.tif .tiff .jpg .jpeg .png` | read with Pillow |

**TIFF layouts.** 16-bit RGB (and 16-bit grayscale, treated as gray RGB) TIFFs are read at full 16-bit precision. 8-bit
TIFFs are read as before. Alpha channels are dropped, only the first page is read, the EXIF orientation is applied.
Other layouts (for example 32-bit float TIFF, palette images) are converted to 8-bit RGB by Pillow, so prefer 16-bit
integer TIFF for scans. Previews are reduced to 1600 px; export decodes the full-resolution file.

The bare-light-source reference for flat-field correction must be a RAW file.

## Export presets
| Preset | Format | Size |
|---|---|---|
| Original · JPEG 100 | JPEG 8-bit, quality 100 | original |
| High quality · JPEG 95 | JPEG 8-bit, quality 95 | original |
| Archive · TIFF 16-bit | TIFF 16-bit, lossless | original |
| Web · 2048 px · JPEG 82 | JPEG | long edge 2048 px |
| Light web · 1280 px · JPEG 72 | JPEG | long edge 1280 px |
| Custom | JPEG or TIFF, your quality and size | your choice |

JPEG uses 4:4:4 chroma at quality 95 and above, 4:2:0 below. Frames marked **PASS** are skipped. If a frame cannot be decoded at full resolution (file moved, damaged), it is **not
exported** and is listed in the summary at the end; SMneg never writes a low-resolution preview in its place.

Exports go into a new folder named from the session (date, title, client, film) inside the destination you
choose. If the folder already exists, `(2)`, `(3)`... is appended: nothing is overwritten.

## Filename templates
The *Name* field accepts these variables (click the chips to insert them). An empty variable is dropped together with
its separator (`A_{city}_B` becomes `A_B`).

| Variable | Value |
|---|---|
| `{seqn}` | sequence number; "001" starts at 1 with 3 digits, "0100" starts at 100 with 4 digits |
| `{filenamebase}` / `{filename}` | original name without / with extension |
| `{date}` | export date (YYYY-MM-DD) |
| `{title}` `{film}` `{client}` `{city}` `{location}` `{photographer}` | session information |

Default template: `{date}_{title}_{seqn}`.

## Metadata
With *Embed metadata* enabled:
- **JPEG**: EXIF `ImageDescription` (session title), `Artist` (photographer), `Copyright`, and a `UserComment`
  containing the full metadata as JSON.
- **TIFF**: XMP (needs `tifffile`): `dc:title`, `dc:description`, `dc:creator`, `dc:rights`, `xmp:CreatorTool`,
  `xmp:CreateDate`, `photoshop:City`, `Iptc4xmpCore:Location`, plus film and client fields. Readable by Lightroom,
  Photoshop, Photo Mechanic and exiftool. Legacy TIFF tags only carry an ASCII version of the text.
- **`metadata.json`** (optional, next to the images): session information, export settings (format, quality, size) and the
  list of exported photos.

## Session files
Each session folder holds `smneg-session.json`: every frame's settings (color, density, rotation, crop, PASS...), the
current frame, the flat-field reference and the session information. It is plain JSON written atomically. Files named
`frontier-session.json` (earlier versions) still open. A session file is checked (structure and types) before it is used;
if it is invalid you get an error message and the current session stays untouched.
