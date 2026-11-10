# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

import cv2
import numpy as np
from PIL import Image, ImageCms
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QCompleter, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from .settings import app_settings
try:
    import tifffile
except ImportError:       # pip install tifffile  (needed to embed metadata in TIFF)
    tifffile = None

TIFF_METADATA_AVAILABLE = tifffile is not None
# Exports are sRGB-encoded (both engines): say so in the file, so every application reads them the same way.
SRGB_ICC = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


@dataclass(frozen=True)
class ExportMetadata:
    date: str
    exported_at: str
    first_name: str
    last_name: str
    film: str
    notes: str
    shoot_title: str
    location: str
    city: str
    photographer: str
    copyright: str


def format_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    if seconds < 60:
        return f"{seconds} s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min {seconds:02d} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min"


def safe_name(value: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value).strip(' .')[:80]


def create_export_folder(parent: Path, metadata: ExportMetadata) -> Path:
    name = ' - '.join(filter(None, (
        metadata.date,
        safe_name(metadata.shoot_title),
        safe_name(f"{metadata.first_name} {metadata.last_name}"),
        safe_name(metadata.film),
    )))
    for sequence in range(1, 10000):
        folder = parent / (name if sequence == 1 else f"{name} ({sequence})")
        try:
            folder.mkdir()
        except FileExistsError:
            continue
        return folder
    raise OSError("Unable to create a unique export folder.")


def _ascii(value) -> str:
    """Legacy TIFF tags only accept ASCII. The full Unicode text goes into XMP."""
    text = str(value or "").replace("©", "(c)")
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").strip()


def build_xmp(metadata: dict) -> bytes:
    """XMP packet readable by Lightroom, Photoshop, Photo Mechanic and exiftool."""
    def text(value):
        return escape(str(value or ""))

    def alt(tag, value):
        return f'<{tag}><rdf:Alt><rdf:li xml:lang="x-default">{text(value)}</rdf:li></rdf:Alt></{tag}>' if value else ""

    client = " ".join(filter(None, (metadata.get("first_name"), metadata.get("last_name"))))
    fields = [
        alt("dc:title", metadata.get("shoot_title")),
        alt("dc:description", metadata.get("notes")),
        f'<dc:creator><rdf:Seq><rdf:li>{text(metadata["photographer"])}</rdf:li></rdf:Seq></dc:creator>'
        if metadata.get("photographer") else "",
        alt("dc:rights", metadata.get("copyright")),
        '<xmpRights:Marked>True</xmpRights:Marked>' if metadata.get("copyright") else "",
        '<xmp:CreatorTool>SMneg</xmp:CreatorTool>',
        f'<xmp:CreateDate>{text(metadata["exported_at"])}</xmp:CreateDate>' if metadata.get("exported_at") else "",
        f'<photoshop:City>{text(metadata["city"])}</photoshop:City>' if metadata.get("city") else "",
        f'<Iptc4xmpCore:Location>{text(metadata["location"])}</Iptc4xmpCore:Location>' if metadata.get("location") else "",
        f'<smneg:Film>{text(metadata["film"])}</smneg:Film>' if metadata.get("film") else "",
        f'<smneg:Client>{text(client)}</smneg:Client>' if client else "",
        f'<smneg:Metadata>{text(json.dumps(metadata, ensure_ascii=False))}</smneg:Metadata>',
    ]
    packet = (
        '<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmlns:xmpRights="http://ns.adobe.com/xap/1.0/rights/" '
        'xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/" '
        'xmlns:Iptc4xmpCore="http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/" '
        'xmlns:smneg="http://smneg.local/ns/1.0/">'
        + "".join(fields) +
        '</rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="w"?>'
    )
    return packet.encode("utf-8")


def save_tiff16(path, pixels, metadata=None, max_edge=0):
    height, width = pixels.shape[:2]
    if max_edge and max(width, height) > max_edge:
        scale = max_edge / max(width, height)
        pixels = cv2.resize(pixels, (max(1, round(width * scale)), max(1, round(height * scale))),
                            interpolation=cv2.INTER_AREA)
    pixels = np.ascontiguousarray(pixels, dtype=np.uint16)
    height, width = pixels.shape[:2]

    if tifffile is not None:
        description, extratags, stamp = None, [], None
        if metadata is not None:
            metadata = {**metadata, "width": width, "height": height}
            description = _ascii(metadata.get("shoot_title")) or None
            for code, key in ((315, "photographer"), (33432, "copyright")):
                value = _ascii(metadata.get(key))
                if value:
                    extratags.append((code, "s", 0, value, True))
            xmp = build_xmp(metadata)
            extratags.append((700, "B", len(xmp), xmp, True))
            try:
                stamp = datetime.fromisoformat(metadata["exported_at"])
            except (KeyError, TypeError, ValueError):
                stamp = None
        try:
            tifffile.imwrite(
                str(path), pixels, photometric="rgb", compression="deflate",
                compressionargs={"level": 1}, metadata=None, description=description,
                software="SMneg", datetime=stamp, extratags=extratags, iccprofile=SRGB_ICC,
            )
        except Exception as error:
            path.unlink(missing_ok=True)
            raise OSError(f"TIFF write failed: {error}") from error
        return width, height

    bgr = cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR)
    try:
        ok = cv2.imwrite(str(path), bgr, [cv2.IMWRITE_TIFF_COMPRESSION, 5])
    except cv2.error as error:
        ok = False
        reason = str(error)
    else:
        reason = "TIFF write failed"
    if not ok:
        path.unlink(missing_ok=True)
        raise OSError(reason)
    return width, height


def save_image(path, pixels, metadata=None, *, quality=100, max_edge=0, file_format="jpeg"):
    if file_format == "tiff":
        return save_tiff16(path, pixels, metadata, max_edge)
    image = Image.fromarray(pixels)
    if max_edge:
        image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    exif = Image.Exif()
    if metadata is not None:
        metadata = {**metadata, "width": image.width, "height": image.height}
        for tag, key in ((270, "shoot_title"), (315, "photographer"), (33432, "copyright")):
            if metadata[key]:
                exif[tag] = metadata[key]
        fields = json.dumps(metadata, ensure_ascii=False)
        exif[37510] = b"UNICODE\x00" + fields.encode("utf-16-be")
    try:
        image.save(path, format="JPEG", quality=quality, subsampling=0 if quality >= 95 else 2, exif=exif,
                   icc_profile=SRGB_ICC)
    except (OSError, ValueError):
        path.unlink(missing_ok=True)
        raise
    return image.size


# ==============================================================================
# filename templates with variables (Photo Mechanic style)
# ==============================================================================
DEFAULT_TEMPLATE = "{date}_{title}_{seqn}"
VARIABLES_HELP = ("{seqn}  {filenamebase}  {filename}  {date}  {title}  "
                  "{film}  {client}  {city}  {location}  {photographer}")
VARIABLE_CHIPS = (
    ("{seqn}", "Sequence number (set the start next to it)"),
    ("{filenamebase}", "Original name without extension"),
    ("{filename}", "Original name with extension"),
    ("{date}", "Export date"),
    ("{title}", "Session title"),
    ("{film}", "Film"),
    ("{client}", "Client first and last name"),
    ("{city}", "City"),
    ("{location}", "Location"),
    ("{photographer}", "Photographer"),
    ("_", "Separator"),
    ("-", "Separator"),
)
VARIABLE_PATTERN = re.compile(r"\{([A-Za-z0-9_]+)\}")


def parse_sequence(text: str) -> tuple[int, int]:
    """Like Photo Mechanic: "001" means start at 1 with 3 digits; "0100" means start at 100 with 4 digits."""
    text = text.strip()
    if not text.isdigit():
        raise ValueError("{seqn}: enter digits only, e.g. 001")
    return int(text), len(text)


EMPTY_MARK = "\x00"
SEPARATORS = "_-. "


def drop_empty_parts(text: str) -> str:
    """An empty variable (e.g. a city with no value) is dropped together with its separator: A_{city}_B → A_B."""
    while EMPTY_MARK in text:
        position = text.index(EMPTY_MARK)
        left = position
        while left > 0 and text[left - 1] in SEPARATORS:
            left -= 1
        right = position + 1
        while right < len(text) and text[right] in SEPARATORS:
            right += 1
        if left == 0 or right == len(text):
            joiner = ""                                   # at the start or the end: no separator
        else:
            joiner = text[left:position][:1] or text[position + 1:right][:1]
        text = text[:left] + joiner + text[right:]
    return text


def build_output_names(template: str, sources: list, fields: dict, sequence_text: str, extension: str) -> list:
    """Returns the output filenames. Raises ValueError if the template is invalid or names collide."""
    template = template.strip()
    if not template:
        raise ValueError("The filename template is empty")
    start, digits = parse_sequence(sequence_text)
    names = []
    for index, source in enumerate(sources or [None]):
        path = Path(source) if source else Path("IMG0001.nef")
        context = {
            **fields,
            "title": fields.get("title") or safe_name(path.stem),
            "seqn": f"{start + index:0{digits}d}",
            "filename": path.name,
            "filenamebase": path.stem,
        }
        unknown = [name for name in VARIABLE_PATTERN.findall(template) if name not in context]
        if unknown:
            raise ValueError(f"Unknown variable: {{{unknown[0]}}}")
        stem = safe_name(drop_empty_parts(VARIABLE_PATTERN.sub(
            lambda match: str(context[match.group(1)]) or EMPTY_MARK, template)))
        if not stem:
            raise ValueError("The filename is empty")
        if "{" in stem or "}" in stem:
            raise ValueError("Invalid braces in the template")
        names.append(f"{stem}.{extension}")
    if not sources:
        return []
    if len({name.lower() for name in names}) != len(names):
        raise ValueError("Duplicate names: add {seqn} to the template")
    return names


DIALOG_STYLE = """
QDialog { background: #1A1C1E; color: #FFFFFF; }
QLabel { color: #C9D1D6; background: transparent; }
QGroupBox { border: 1px solid #2E3236; border-radius: 6px; margin-top: 14px; padding: 14px 10px 8px 10px;
            color: #00E5FF; font-weight: bold; background: #1D1F22; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }
QLineEdit, QSpinBox, QComboBox { background: #2A2E32; border: 1px solid #454B51; border-radius: 4px;
            padding: 3px 8px; color: #FFFFFF; min-height: 24px; selection-background-color: #00838F; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border: 1px solid #00E5FF; }
QLineEdit[invalid="true"] { border: 1px solid #FF5252; }
QComboBox QAbstractItemView { background: #2A2E32; color: #FFFFFF; selection-background-color: #00838F; }
QListWidget { background: #141517; border: 1px solid #2E3236; border-radius: 4px; color: #E0E6EA; }
QListWidget::item { padding: 3px 4px; }
QCheckBox { color: #E0E6EA; spacing: 8px; background: transparent; }
QCheckBox::indicator, QListWidget::indicator { width: 16px; height: 16px; border: 1px solid #6B7278;
            border-radius: 3px; background: #2A2E32; }
QCheckBox::indicator:checked, QListWidget::indicator:checked { background: #00E5FF; border: 1px solid #00E5FF; }
QPushButton { background: #37474F; color: #FFFFFF; border: 1px solid #111; border-radius: 4px;
            padding: 6px 14px; font-weight: bold; }
QPushButton:hover { background: #455A64; }
QPushButton:disabled { background: #25292C; color: #6B7278; }
QPushButton#chip { background: #2A2E32; color: #80DFAB; border: 1px solid #454B51; border-radius: 10px;
            padding: 0px 10px; font-size: 12px; font-weight: normal; }
QPushButton#chip:hover { background: #00838F; color: #FFFFFF; border: 1px solid #00E5FF; }
QPushButton#primary { background: #00838F; }
QPushButton#primary:hover { background: #0097A7; }
QPushButton#primary:disabled { background: #25292C; color: #6B7278; }
"""


class ExportDialog(QDialog):
    PRESETS = (
        ("Original · JPEG 100", ("jpeg", 100, 0)),
        ("High quality · JPEG 95", ("jpeg", 95, 0)),
        ("Archive · TIFF 16-bit", ("tiff", 100, 0)),
        ("Web · 2048 px · JPEG 82", ("jpeg", 82, 2048)),
        ("Light web · 1280 px · JPEG 72", ("jpeg", 72, 1280)),
        ("Custom", None),
    )

    def __init__(self, frames, parent, info=None, current_index=None):
        super().__init__(parent)
        self.current_index = current_index
        self.settings = app_settings()
        self._refreshing = False
        self.frames = [frame for frame in frames if not frame.is_passed]
        self.setWindowTitle("Export scans")
        self.setStyleSheet(DIALOG_STYLE)
        self.resize(940, 720)   # no setMinimumSize: the layout defines the minimum so the buttons are not squashed

        self.date = QLabel(datetime.now().astimezone().date().isoformat())
        self.first_name = self.line("First name")
        self.last_name = self.line("Last name")
        self.film = self.line("e.g. Kodak Portra 400")
        self.shoot_title = self.line("e.g. Ahmed & Salma wedding")
        self.location = self.line("Location")
        self.city = self.line("City")
        self.notes = self.line("Notes")
        self.photographer = self.line("Photographer")
        self.copyright = self.line("© 2026 Your Name")
        self.destination = self.line("Choose the destination folder…")

        root = QVBoxLayout(self)
        root.setSpacing(10)

        # ---- destination (required, at the top) ----
        destination_row = QHBoxLayout()
        destination_row.addWidget(QLabel("Destination"))
        destination_row.addWidget(self.destination, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.choose_destination)
        destination_row.addWidget(browse)
        root.addLayout(destination_row)

        columns = QHBoxLayout()
        columns.setSpacing(12)
        root.addLayout(columns, 1)

        # ---- left column: metadata ----
        left = QVBoxLayout()
        columns.addLayout(left, 5)
        left.addWidget(self.group("Session", (
            ("Title", self.shoot_title), ("Location · City", self.pair(self.location, self.city)),
            ("Notes", self.notes), ("Export date", self.date),
        )))
        left.addWidget(self.group("Client and film", (
            ("First · Last name", self.pair(self.first_name, self.last_name)), ("Film", self.film),
        )))
        left.addWidget(self.group("Author", (
            ("Photographer", self.photographer), ("Copyright", self.copyright),
        )))
        left.addStretch(1)

        # ---- right column: files + list ----
        right = QVBoxLayout()
        columns.addLayout(right, 6)

        self.preset = QComboBox()
        for label, values in self.PRESETS:
            self.preset.addItem(label, values)
        self.preset_info = QLabel()
        self.file_format = QComboBox()
        self.file_format.addItem("JPEG 8-bit", "jpeg")
        self.file_format.addItem("TIFF 16-bit", "tiff")
        self.quality = QSpinBox()
        self.quality.setRange(1, 100)
        self.max_edge = QSpinBox()
        self.max_edge.setRange(0, 50000)
        self.max_edge.setSpecialValueText("Original size")
        self.max_edge.setSuffix(" px")
        self.custom_box = QWidget()
        custom_form = self.make_form(self.custom_box)
        custom_form.addRow("Format", self.file_format)
        custom_form.addRow("JPEG quality", self.quality)
        custom_form.addRow("Longest side", self.max_edge)

        self.template = self.line(DEFAULT_TEMPLATE)
        self.template.setText(DEFAULT_TEMPLATE)
        self.template.setToolTip("Variables: " + VARIABLES_HELP)
        self.sequence_text = self.line("001")
        self.sequence_text.setText("001")
        self.sequence_text.setMaximumWidth(110)
        self.sequence_text.setToolTip("Start of {seqn}. Leading zeros set the digit count: 001 → 001, 002…")
        self.name_hint = QLabel()
        self.name_hint.setWordWrap(True)
        variables = QWidget()
        chips = QGridLayout(variables)
        chips.setContentsMargins(0, 0, 0, 0)
        chips.setSpacing(6)
        self.variable_buttons = {}
        for position, (token, description) in enumerate(VARIABLE_CHIPS):
            chip = QPushButton(token)
            chip.setObjectName("chip")
            chip.setToolTip(description)
            chip.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # keeps the cursor in the name field
            chip.setFixedHeight(26)
            chip.clicked.connect(lambda checked=False, token=token: self.insert_token(token))
            chips.addWidget(chip, position // 4, position % 4)
            self.variable_buttons[token] = chip
        reset = QPushButton("Reset")
        reset.setObjectName("chip")
        reset.setToolTip("Restore the default template")
        reset.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        reset.setFixedHeight(26)
        reset.clicked.connect(lambda checked=False: self.template.setText(DEFAULT_TEMPLATE))
        chips.addWidget(reset, len(VARIABLE_CHIPS) // 4, len(VARIABLE_CHIPS) % 4)

        files_group = self.group("Files", (
            ("Profile", self.preset), ("", self.preset_info), ("", self.custom_box),
            ("Name", self.template), ("{seqn} start", self.sequence_text),
        ))
        files_group.form.addRow("Variables", variables)
        files_group.form.addRow("", self.name_hint)
        right.addWidget(files_group)

        photos_group = QGroupBox("Photos")
        photos_layout = QVBoxLayout(photos_group)
        self.count_label = QLabel()
        self.photos = QListWidget()
        self.photos.setMinimumHeight(150)
        for frame in self.frames:
            row = QListWidgetItem(Path(frame.path).name, self.photos)
            row.setData(Qt.ItemDataRole.UserRole, frame.index)
            row.setCheckState(Qt.CheckState.Checked)
        selection = QHBoxLayout()
        selection.addWidget(self.count_label, 1)
        for label, state in (("Select all", Qt.CheckState.Checked),
                             ("Select none", Qt.CheckState.Unchecked)):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, state=state: self.set_checked(state))
            selection.addWidget(button)
        self.btn_current = QPushButton("Current frame")
        self.btn_current.setEnabled(any(frame.index == current_index for frame in self.frames))
        self.btn_current.clicked.connect(self.select_current)
        selection.addWidget(self.btn_current)
        photos_layout.addLayout(selection)
        photos_layout.addWidget(self.photos, 1)
        right.addWidget(photos_group, 1)

        # ---- bottom ----
        self.embed = QCheckBox("Embed metadata in the files (EXIF for JPEG · XMP for TIFF)")
        self.sidecar = QCheckBox("Create a metadata.json file for the batch")
        root.addWidget(self.embed)
        root.addWidget(self.sidecar)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.submit = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.submit.setObjectName("primary")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.load_settings()
        self.apply_info(info)
        for field in (self.first_name, self.last_name, self.film, self.shoot_title, self.location,
                      self.city, self.photographer, self.template, self.sequence_text, self.destination):
            field.textChanged.connect(self.refresh)
        self.preset.currentIndexChanged.connect(self.update_preset)
        self.file_format.currentIndexChanged.connect(self.refresh)
        self.quality.valueChanged.connect(self.refresh)
        self.max_edge.valueChanged.connect(self.refresh)
        self.photos.itemChanged.connect(self.refresh)
        self.update_preset()

    # ---- helpers de construction ----
    @staticmethod
    def line(placeholder=""):
        field = QLineEdit()
        field.setPlaceholderText(placeholder)
        return field

    @staticmethod
    def make_form(parent=None):
        form = QFormLayout(parent)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setContentsMargins(0, 0, 0, 0)
        form.setVerticalSpacing(8)
        return form

    @staticmethod
    def pair(first, second):
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(first, 1)
        layout.addWidget(second, 1)
        return box

    def group(self, title, rows):
        box = QGroupBox(title)
        form = self.make_form()
        box.setLayout(form)
        box.form = form
        for label, field in rows:
            form.addRow(label, field)
        return box

    def insert_token(self, token):
        """Inserts the variable at the cursor (or replaces the selected text) in the name field."""
        self.template.insert(token)
        self.template.setFocus()

    # ---- state ----
    def load_settings(self):
        settings = self.settings
        self.photographer.setText(settings.value("export/photographer", "", type=str))
        self.copyright.setText(settings.value("export/copyright", "", type=str))
        destination = settings.value("export/destination", "", type=str)
        if destination and Path(destination).is_dir():
            self.destination.setText(destination)
        self.template.setText(settings.value("export/template", DEFAULT_TEMPLATE, type=str) or DEFAULT_TEMPLATE)
        index = settings.value("export/preset", 0, type=int)
        self.preset.setCurrentIndex(index if 0 <= index < self.preset.count() else 0)
        if self.preset.currentData() is None:
            self.file_format.setCurrentIndex(max(0, self.file_format.findData(settings.value("export/format", "jpeg", type=str))))
            self.quality.setValue(settings.value("export/quality", 95, type=int))
            self.max_edge.setValue(settings.value("export/max_edge", 0, type=int))
        self.embed.setChecked(settings.value("export/embed", True, type=bool))
        self.sidecar.setChecked(settings.value("export/sidecar", True, type=bool))

    INFO_FIELDS = ("shoot_title", "first_name", "last_name", "film", "location", "city", "notes", "photographer", "copyright")

    def apply_info(self, info):
        for key in self.INFO_FIELDS:
            value = (info or {}).get(key, "")
            if isinstance(value, str) and value.strip():
                getattr(self, key).setText(value.strip())

    def info(self):
        return {key: getattr(self, key).text().strip() for key in self.INFO_FIELDS}

    def save_settings(self):
        settings = self.settings
        settings.setValue("export/photographer", self.photographer.text().strip())
        settings.setValue("export/copyright", self.copyright.text().strip())
        settings.setValue("export/destination", self.destination.text().strip())
        settings.setValue("export/template", self.template.text().strip())
        settings.setValue("export/preset", self.preset.currentIndex())
        settings.setValue("export/format", self.file_format.currentData())
        settings.setValue("export/quality", self.quality.value())
        settings.setValue("export/max_edge", self.max_edge.value())
        settings.setValue("export/embed", self.embed.isChecked())
        settings.setValue("export/sidecar", self.sidecar.isChecked())

    def accept(self):
        self.save_settings()
        super().accept()

    def update_preset(self, *_):
        values = self.preset.currentData()
        self.custom_box.setVisible(values is None)
        if values is not None:
            file_format, quality, max_edge = values
            self.file_format.setCurrentIndex(self.file_format.findData(file_format))
            self.quality.setValue(quality)
            self.max_edge.setValue(max_edge)
        self.refresh()

    def set_checked(self, state):
        for index in range(self.photos.count()):
            self.photos.item(index).setCheckState(state)

    def select_current(self):
        for index in range(self.photos.count()):
            row = self.photos.item(index)
            row.setCheckState(Qt.CheckState.Checked if row.data(Qt.ItemDataRole.UserRole) == self.current_index
                              else Qt.CheckState.Unchecked)

    def selected_indices(self):
        return {
            row.data(Qt.ItemDataRole.UserRole)
            for index in range(self.photos.count())
            if (row := self.photos.item(index)).checkState() == Qt.CheckState.Checked
        }

    def extension(self):
        return "tif" if self.file_format.currentData() == "tiff" else "jpg"

    def sequence_parameters(self):
        return parse_sequence(self.sequence_text.text())

    def name_fields(self):
        metadata = self.metadata()
        return {
            "date": metadata.date,
            "title": safe_name(metadata.shoot_title),
            "film": safe_name(metadata.film),
            "client": safe_name(f"{metadata.first_name} {metadata.last_name}"),
            "city": safe_name(metadata.city),
            "location": safe_name(metadata.location),
            "photographer": safe_name(metadata.photographer),
        }

    def output_names(self, frames, extension=None):
        """Output filenames for the photos (same order). Raises ValueError if the template is invalid."""
        return build_output_names(
            self.template.text(), [frame.path for frame in frames], self.name_fields(),
            self.sequence_text.text(), extension or self.extension(),
        )

    def flag_invalid(self, widget, invalid):
        if widget.property("invalid") != invalid:
            widget.setProperty("invalid", invalid)
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def refresh(self, *_):
        """Updates the names, the counter, the hint and the Export button."""
        if self._refreshing:
            return
        self._refreshing = True
        try:
            rows = [self.photos.item(index) for index in range(self.photos.count())]
            checked = [(row, frame) for row, frame in zip(rows, self.frames)
                       if row.checkState() == Qt.CheckState.Checked]
            error, names = None, []
            try:
                names = self.output_names([frame for _, frame in checked])   # validates the template even with no photos
            except ValueError as problem:
                error = str(problem)

            outputs = {id(row): name for (row, _), name in zip(checked, names)}
            for row, frame in zip(rows, self.frames):
                source = Path(frame.path).name
                text = f"{source}   →   {outputs[id(row)]}" if id(row) in outputs else source
                if row.text() != text:
                    row.setText(text)

            self.count_label.setText(f"{len(checked)} / {len(rows)} photos selected")
            if error:
                self.name_hint.setText(error)
                self.name_hint.setStyleSheet("color: #FF5252;")
            else:
                self.name_hint.setText(f"Example: {names[0]}" if names else "")
                self.name_hint.setStyleSheet("color: #80DFAB;")
            values = self.preset.currentData() or (self.file_format.currentData(), self.quality.value(), self.max_edge.value())
            file_format, quality, max_edge = values
            size = f"{max_edge} px" if max_edge else "original size"
            self.preset_info.setText(
                f"{'TIFF 16-bit · lossless' if file_format == 'tiff' else f'JPEG 8-bit · quality {quality}'} · {size}")
            self.preset_info.setStyleSheet("color: #7F8A91; font-size: 11px;")
            self.quality.setEnabled(self.file_format.currentData() == "jpeg")

            has_destination = bool(self.destination.text().strip())
            self.flag_invalid(self.destination, not has_destination)
            sequence_error = bool(error and error.startswith("{seqn}"))
            self.flag_invalid(self.template, bool(error) and not sequence_error)
            self.flag_invalid(self.sequence_text, sequence_error)
            label = self.file_format.currentData().upper()
            self.submit.setText(f"Export {len(checked)} {label}" if checked else "Export")
            self.submit.setEnabled(bool(has_destination and checked and error is None))
        finally:
            self._refreshing = False

    def choose_destination(self):
        start = self.destination.text() or self.settings.value("export/destination", "", type=str)
        folder = QFileDialog.getExistingDirectory(self, "Destination folder", start)
        if folder:
            self.destination.setText(folder)

    def metadata(self):
        now = datetime.now().astimezone()
        return ExportMetadata(
            now.date().isoformat(), now.isoformat(timespec="seconds"), self.first_name.text().strip(),
            self.last_name.text().strip(), self.film.text().strip(), self.notes.text().strip(),
            self.shoot_title.text().strip(), self.location.text().strip(), self.city.text().strip(),
            self.photographer.text().strip(), self.copyright.text().strip(),
        )


class SessionInfoDialog(QDialog):
    """All session information is typed once at the start of a session and pre-fills the Export dialog."""
    SECTIONS = (
        ("Session", (
            ("shoot_title", "Session title *", "e.g. Ahmed & Salma wedding"),
            ("location", "Location", "e.g. Palmeraie"),
            ("city", "City", "e.g. Marrakech"),
            ("notes", "Notes", "Free notes"),
        )),
        ("Client", (
            ("first_name", "First name", "First name"),
            ("last_name", "Last name", "Last name"),
        )),
        ("Film", (
            ("film", "Film", "e.g. Kodak Portra 400"),
        )),
        ("Copyright", (
            ("photographer", "Photographer", "Your name"),
            ("copyright", "Copyright", "© 2026 Your Name"),
        )),
    )
    FIELDS = tuple(field for _, group in SECTIONS for field in group)
    NO_PRESET = "— No preset —"
    HISTORY_LIMIT = 20

    def __init__(self, parent=None, info=None, title="Session information"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setStyleSheet(DIALOG_STYLE)
        self.resize(680, 700)
        self.settings = app_settings()
        info = dict(info or {})
        for key in ("photographer", "copyright"):
            if not str(info.get(key, "")).strip():
                info[key] = self.settings.value(f"export/{key}", "", type=str)
        self.edits = {}

        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ---- presets ----
        presets_row = QHBoxLayout()
        presets_row.addWidget(QLabel("Preset"))
        self.presets = QComboBox()
        self.presets.setMinimumWidth(220)
        presets_row.addWidget(self.presets, 1)
        self.btn_save_preset = QPushButton("Save as preset")
        self.btn_delete_preset = QPushButton("Delete")
        presets_row.addWidget(self.btn_save_preset)
        presets_row.addWidget(self.btn_delete_preset)
        root.addLayout(presets_row)

        # ---- sections ----
        for section, fields in self.SECTIONS:
            box = QGroupBox(section)
            form = QFormLayout(box)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            form.setHorizontalSpacing(16)
            for key, label, placeholder in fields:
                edit = QLineEdit()
                edit.setMinimumWidth(360)
                edit.setPlaceholderText(placeholder)
                edit.setText(str(info.get(key, "") or ""))
                completer = QCompleter(self.history(key), edit)
                completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                edit.setCompleter(completer)
                edit.textChanged.connect(self.refresh)
                self.edits[key] = edit
                form.addRow(label, edit)
            root.addWidget(box)

        self.preview = QLabel()
        self.preview.setWordWrap(True)
        root.addWidget(self.preview)
        self.error = QLabel()
        self.error.setStyleSheet("color: #FF5252;")
        root.addWidget(self.error)
        hint = QLabel("This information is filled in automatically in the export dialog (editable there).")
        hint.setWordWrap(True)
        root.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setObjectName("primary")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.reload_presets()
        self.presets.activated.connect(self.apply_preset)
        self.btn_save_preset.clicked.connect(self.save_preset)
        self.btn_delete_preset.clicked.connect(self.delete_preset)
        self.refresh()

    # ---- history (autocompletion) ----
    def history(self, key):
        try:
            values = json.loads(self.settings.value(f"session_history/{key}", "[]", type=str))
        except ValueError:
            return []
        return [value for value in values if isinstance(value, str)]

    def remember(self, info):
        for key, value in info.items():
            value = value.strip()
            if not value:
                continue
            values = [item for item in self.history(key) if item.lower() != value.lower()]
            self.settings.setValue(f"session_history/{key}", json.dumps([value] + values[: self.HISTORY_LIMIT - 1], ensure_ascii=False))

    # ---- presets ----
    def load_presets(self):
        try:
            data = json.loads(self.settings.value("session_presets", "{}", type=str))
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def reload_presets(self, select=None):
        presets = self.load_presets()
        self.presets.clear()
        self.presets.addItem(self.NO_PRESET)
        for name in sorted(presets, key=str.lower):
            self.presets.addItem(name)
        if select:
            self.presets.setCurrentIndex(max(0, self.presets.findText(select)))
        self.btn_delete_preset.setEnabled(self.presets.currentIndex() > 0)

    def apply_preset(self, *_):
        name = self.presets.currentText()
        self.btn_delete_preset.setEnabled(self.presets.currentIndex() > 0)
        values = self.load_presets().get(name)
        if not isinstance(values, dict):
            return
        for key, edit in self.edits.items():
            edit.setText(str(values.get(key, "") or ""))

    def save_preset(self):
        name, ok = QInputDialog.getText(self, "Preset", "Preset name:", text=self.edits["shoot_title"].text().strip())
        name = name.strip()
        if not ok or not name:
            return
        presets = self.load_presets()
        presets[name] = self.info()
        self.settings.setValue("session_presets", json.dumps(presets, ensure_ascii=False))
        self.reload_presets(select=name)

    def delete_preset(self):
        name = self.presets.currentText()
        presets = self.load_presets()
        if presets.pop(name, None) is not None:
            self.settings.setValue("session_presets", json.dumps(presets, ensure_ascii=False))
        self.reload_presets()

    # ---- validation + preview ----
    def refresh(self, *_):
        info = self.info()
        title_edit = self.edits["shoot_title"]
        missing = not info["shoot_title"]
        title_edit.setProperty("invalid", missing)
        title_edit.style().unpolish(title_edit)
        title_edit.style().polish(title_edit)
        warnings = []
        if missing:
            warnings.append("The session title is required.")
        if not info["photographer"] or not info["copyright"]:
            warnings.append("Photographer / Copyright are empty: they will not be written into the files.")
        self.error.setText("\n".join(warnings))
        self.ok_button.setEnabled(not missing)
        name = " - ".join(filter(None, (
            datetime.now().astimezone().date().isoformat(), safe_name(info["shoot_title"]),
            safe_name(f"{info['first_name']} {info['last_name']}"), safe_name(info["film"]),
        )))
        self.preview.setText(f"Export folder: {name}")

    def accept(self):
        if not self.info()["shoot_title"]:
            return
        info = self.info()
        self.remember(info)
        self.settings.sync()
        super().accept()

    def info(self):
        return {key: edit.text().strip() for key, edit in self.edits.items()}
