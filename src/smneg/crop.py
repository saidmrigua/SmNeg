# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
from __future__ import annotations

import math

import cv2
import numpy as np
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QLabel, QPushButton, QRubberBand,
    QVBoxLayout,
)

CropBounds = tuple[float, float, float, float]


def straighten_image(image: np.ndarray, angle: float) -> np.ndarray:
    if not angle:
        return image
    height, width = image.shape[:2]
    radians = math.radians(angle)
    cosine, sine = abs(math.cos(radians)), abs(math.sin(radians))
    scale = cosine + sine * max(width / height, height / width)
    center = ((width - 1) / 2, (height - 1) / 2)
    transform = cv2.getRotationMatrix2D(center, angle, scale)
    return cv2.warpAffine(image, transform, (width, height),
                          flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def rotate_bounds(bounds: CropBounds, clockwise: bool) -> CropBounds:
    """The same crop box after the image is turned by 90 degrees (all values are fractions of the image size)."""
    left, top, right, bottom = bounds
    if clockwise:
        return (1 - bottom, left, 1 - top, right)
    return (top, 1 - right, bottom, 1 - left)


def flip_bounds(bounds: CropBounds) -> CropBounds:
    """The same crop box after the image is mirrored left to right."""
    left, top, right, bottom = bounds
    return (1 - right, top, 1 - left, bottom)


def to_source_bounds(bounds: CropBounds, rotation: int, mirror: bool) -> CropBounds:
    """Crop box on the displayed image (mirrored, then rotated clockwise) -> box on the untouched source frame."""
    for _ in range((rotation % 360) // 90):
        bounds = rotate_bounds(bounds, clockwise=False)
    return flip_bounds(bounds) if mirror else tuple(bounds)


def from_source_bounds(bounds: CropBounds, rotation: int, mirror: bool) -> CropBounds:
    """Crop box on the untouched source frame -> box on the displayed image."""
    if mirror:
        bounds = flip_bounds(bounds)
    for _ in range((rotation % 360) // 90):
        bounds = rotate_bounds(bounds, clockwise=True)
    return tuple(bounds)


def reorient(bounds: CropBounds | None, straighten: float, old: tuple[int, bool], new: tuple[int, bool]):
    """Keep a manual crop and the straighten angle on the same picture content when rotation or mirror changes.
    `old` and `new` are (rotation, mirror). Returns (bounds, straighten)."""
    if bounds is not None:
        bounds = from_source_bounds(to_source_bounds(bounds, *old), *new)
    if straighten and old[1] != new[1]:
        straighten = -straighten          # mirroring reverses the direction of a small rotation
    return bounds, straighten


def apply_crop(image: np.ndarray, bounds: CropBounds | None) -> np.ndarray:
    if bounds is None:
        return image
    height, width = image.shape[:2]
    left, top, right, bottom = bounds
    x = min(width - 1, round(left * width))
    y = min(height - 1, round(top * height))
    return image[y:max(y + 1, round(bottom * height)), x:max(x + 1, round(right * width))]


class CropPreview(QLabel):
    def __init__(self, image, bounds, on_line):
        super().__init__()
        self.image = image
        self.on_line = on_line
        self.line_mode = False
        self.point_a = None
        self.set_angle(0)
        self.setFixedSize(self.pixmap().size())
        self.band = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self.initial_bounds = bounds
        self.selection = self.rect()
        if bounds is not None:
            l, t, r, b = bounds
            self.selection = QRect(round(l * self.width()), round(t * self.height()),
                                   max(1, round((r - l) * self.width())),
                                   max(1, round((b - t) * self.height())))
        self.initial_selection = QRect(self.selection)
        self.ratio = None
        self.origin = None
        self.move_offset = None
        self.show_selection()

    def set_angle(self, angle):
        image = straighten_image(self.image, angle)
        pixels = np.ascontiguousarray(image)
        h, w = pixels.shape[:2]
        qimage = QImage(pixels.data, w, h, pixels.strides[0], QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimage).scaled(780, 500, Qt.AspectRatioMode.KeepAspectRatio,
                                                   Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(pixmap)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.point_a is not None:
            painter = QPainter(self)
            painter.setPen(QColor("#00E5FF"))
            painter.drawEllipse(self.point_a, 4, 4)
            painter.drawText(self.point_a + QPoint(8, -5), "A")

    def set_line_mode(self, active):
        self.line_mode = active
        self.point_a = None
        self.band.setVisible(not active)
        self.setCursor(Qt.CursorShape.CrossCursor if active else Qt.CursorShape.ArrowCursor)
        self.update()

    def show_selection(self):
        self.band.setGeometry(self.selection)
        self.band.setVisible(not self.line_mode)

    def set_ratio(self, ratio):
        self.ratio = ratio
        width, height = self.width(), self.height()
        if ratio:
            width = min(width, max(1, round(height * ratio)))
            height = min(height, max(1, round(width / ratio)))
        self.selection = QRect((self.width() - width) // 2, (self.height() - height) // 2,
                               width, height)
        self.show_selection()

    def redraw(self):
        self.selection = self.rect()
        self.show_selection()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.line_mode:
                point = event.position().toPoint()
                if self.point_a is None:
                    self.point_a = point
                    self.update()
                elif (point - self.point_a).manhattanLength() >= 5:
                    delta = point - self.point_a
                    height, width = self.image.shape[:2]
                    angle = math.degrees(math.atan2(delta.y() * height / self.height(),
                                                     delta.x() * width / self.width()))
                    self.on_line((angle + 45) % 90 - 45)
                return
            self.origin = event.position().toPoint()
            self.move_offset = None
            if self.selection != self.rect() and self.selection.contains(self.origin):
                self.move_offset = self.origin - self.selection.topLeft()

    def mouseMoveEvent(self, event):
        if self.origin is None:
            return
        point = event.position().toPoint()
        if self.move_offset is not None:
            target = point - self.move_offset
            self.selection.moveTo(
                min(max(0, target.x()), self.width() - self.selection.width()),
                min(max(0, target.y()), self.height() - self.selection.height()),
            )
        else:
            x = min(max(0, point.x()), self.width() - 1)
            y = min(max(0, point.y()), self.height() - 1)
            dx, dy = x - self.origin.x(), y - self.origin.y()
            width, height = abs(dx) + 1, abs(dy) + 1
            if self.ratio:
                width = min(width, max(1, round(height * self.ratio)))
                height = min(height, max(1, round(width / self.ratio)))
            corner = self.origin - QPoint(width - 1 if dx < 0 else 0, height - 1 if dy < 0 else 0)
            self.selection = QRect(corner.x(), corner.y(), width, height)
        self.show_selection()

    def mouseReleaseEvent(self, event):
        self.origin = None

    def bounds(self):
        rect = self.selection
        if self.initial_bounds is not None and rect.size() == self.initial_selection.size():
            left, top, right, bottom = self.initial_bounds
            dx = (rect.x() - self.initial_selection.x()) / self.width()
            dy = (rect.y() - self.initial_selection.y()) / self.height()
            dx = min(max(-left, dx), 1 - right)
            dy = min(max(-top, dy), 1 - bottom)
            return left + dx, top + dy, right + dx, bottom + dy
        return (rect.x() / self.width(), rect.y() / self.height(),
                (rect.x() + rect.width()) / self.width(), (rect.y() + rect.height()) / self.height())


class ManualCropDialog(QDialog):
    def __init__(self, image, bounds, parent, angle=0.0):
        super().__init__(parent)
        self.setWindowTitle("Manual Crop")
        self.preview = CropPreview(image, bounds, self.apply_line)
        self.crop = bounds
        layout = QVBoxLayout(self)
        formats = QComboBox()
        formats.addItem("Libre", None)
        for width, height in ((1, 1), (4, 5), (2, 3), (3, 4), (6, 7), (6, 8), (6, 9), (16, 9)):
            formats.addItem(f"{width}:{height}", width / height)
            if width != height:
                formats.addItem(f"{height}:{width}", height / width)
        formats.currentIndexChanged.connect(lambda: self.preview.set_ratio(formats.currentData()))
        layout.addWidget(formats)
        self.angle = QDoubleSpinBox()
        self.angle.setRange(-45, 45)
        self.angle.setSingleStep(0.1)
        self.angle.setSuffix("°")
        self.angle.setValue(angle)
        self.angle.valueChanged.connect(self.preview.set_angle)
        self.preview.set_angle(angle)
        layout.addWidget(QLabel("Straighten"))
        layout.addWidget(self.angle)
        self.line_button = QPushButton("Draw line A → B")
        self.line_button.setCheckable(True)
        self.line_button.toggled.connect(self.preview.set_line_mode)
        layout.addWidget(self.line_button)
        layout.addWidget(QLabel("Draw a frame from outside the current frame. Drag inside it to move it."))
        layout.addWidget(self.preview, alignment=Qt.AlignmentFlag.AlignCenter)
        redraw = QPushButton("Redraw frame")
        redraw.clicked.connect(self.preview.redraw)
        layout.addWidget(redraw)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        remove = buttons.addButton("Remove crop", QDialogButtonBox.ButtonRole.ResetRole)
        remove.clicked.connect(self.remove_crop)
        buttons.accepted.connect(self.apply_selection)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def apply_line(self, correction):
        self.angle.setValue((self.angle.value() + correction + 45) % 90 - 45)
        self.line_button.setChecked(False)

    def apply_selection(self):
        self.crop = self.preview.bounds()
        self.accept()

    def remove_crop(self):
        self.crop = None
        self.accept()
