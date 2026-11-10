# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Said Mrigua
from __future__ import annotations

from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from .models import FrameItem


class FrameCard(QFrame):
    clicked = Signal(int)
    doubleClicked = Signal(int)

    def __init__(self, slot_id: int, parent=None):
        super().__init__(parent)
        self.slot_id = slot_id
        self.frame_idx = -1
        self._pixmap = QPixmap()
        self.init_ui()

    def init_ui(self):
        self.setFrameShape(QFrame.Shape.Box)
        self.setLineWidth(2)
        self.setStyleSheet("background-color: #24272A; border: 2px solid #18191B;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        card_header = QHBoxLayout()
        self.lbl_id = QLabel(f"#{self.slot_id + 1:02d}")
        self.lbl_id.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        self.lbl_id.setStyleSheet("color: white; background: #1B1D1F; padding: 1px 4px; border-radius: 2px;")
        card_header.addWidget(self.lbl_id)
        card_header.addStretch()

        self.lbl_crop_indicator = QLabel("CROP:OFF")
        self.lbl_crop_indicator.setFont(QFont("Arial", 7, QFont.Weight.Bold))
        self.lbl_crop_indicator.setStyleSheet("color: #888;")
        card_header.addWidget(self.lbl_crop_indicator)
        layout.addLayout(card_header)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: #0E0F10; border: 1px solid #000;")
        self.image_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        layout.addWidget(self.image_label, stretch=1)

        info = QHBoxLayout()
        info.setSpacing(3)
        self.lbl_c = QLabel("C:0")
        self.lbl_m = QLabel("M:0")
        self.lbl_y = QLabel("Y:0")
        self.lbl_d = QLabel("D:0")
        for lbl in (self.lbl_c, self.lbl_m, self.lbl_y, self.lbl_d):
            lbl.setFont(QFont("Consolas", 8))
            lbl.setStyleSheet("color: #D6D6D6; background: #1E2022; padding: 2px;")
            info.addWidget(lbl)

        self.lbl_status = QLabel("READY")
        self.lbl_status.setFont(QFont("Arial", 8, QFont.Weight.Bold))
        self.lbl_status.setStyleSheet("color: #00E5FF; background: #111; padding: 2px 4px;")
        info.addWidget(self.lbl_status)
        layout.addLayout(info)

    def mousePressEvent(self, event):
        if self.frame_idx != -1 and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.frame_idx)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.frame_idx != -1 and event.button() == Qt.MouseButton.LeftButton:
            self.doubleClicked.emit(self.frame_idx)
        super().mouseDoubleClickEvent(event)

    def set_active(self, active: bool):
        border = "#00E5FF" if active else "#18191B"
        bg = "#32363B" if active else "#24272A"
        self.setStyleSheet(f"background-color: {bg}; border: 2px solid {border};")

    def update_card(self, item: Optional[FrameItem], rendered: Optional[np.ndarray]):
        if item is None or rendered is None:
            self.frame_idx = -1
            self.image_label.clear()
            self._pixmap = QPixmap()
            self.lbl_id.setText(f"#{self.slot_id + 1:02d}")
            self.lbl_c.setText("C:0")
            self.lbl_m.setText("M:0")
            self.lbl_y.setText("Y:0")
            self.lbl_d.setText("D:0")
            self.lbl_status.setText("-")
            self.lbl_crop_indicator.setText("")
            return

        self.frame_idx = item.index
        mirror_tag = " [M]" if item.mirror else ""
        self.lbl_id.setText(f"#{item.index + 1:02d} ({item.rotation}°){mirror_tag}")
        self.lbl_crop_indicator.setText("CROP:ON" if item.auto_crop else "CROP:OFF")
        self.lbl_crop_indicator.setStyleSheet("color: #00E5FF;" if item.auto_crop else "color: #777;")

        self.lbl_c.setText(f"C:{item.cyan:+d}")
        self.lbl_m.setText(f"M:{item.magenta:+d}")
        self.lbl_y.setText(f"Y:{item.yellow:+d}")
        self.lbl_d.setText(f"D:{item.density:+d}")

        if item.is_passed:
            self.lbl_status.setText("PASS")
            self.lbl_status.setStyleSheet("color: #FF5252; background: #330000; padding: 2px;")
        else:
            self.lbl_status.setText("READY")
            self.lbl_status.setStyleSheet("color: #00FF66; background: #111; padding: 2px;")

        disp = rendered.copy()
        if item.is_passed:
            mark_passed(disp)

        h, w, ch = disp.shape
        qimg = QImage(disp.data, w, h, ch * w, QImage.Format.Format_RGB888)
        self._pixmap = QPixmap.fromImage(qimg)
        self._scale()

    def _scale(self):
        if not self._pixmap.isNull() and self.image_label.width() > 10 and self.image_label.height() > 10:
            self.image_label.setPixmap(self._pixmap.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._scale()


# ==============================================================================
# 4. ENLARGED SINGLE-FRAME PREVIEW
# ==============================================================================
# ==============================================================================
# In-place ZOOM (no popup)
# ==============================================================================
def fit_width(canvas_w: float, canvas_h: float, aspect: float) -> float:
    """Displayed width of the image when it is \"fit\" in the canvas."""
    return max(1.0, min(canvas_w, canvas_h * aspect))


def clamp_center(canvas_w, canvas_h, disp_w, disp_h, cx, cy):
    """Keeps the image inside the frame; if it is smaller than the frame it is centered."""
    def one(size, disp, center):
        if disp <= size:
            return 0.5
        half = size / 2 / disp
        return min(max(center, half), 1 - half)
    return one(canvas_w, disp_w, cx), one(canvas_h, disp_h, cy)


def mark_passed(image: np.ndarray) -> None:
    """Draw a large PASS mark centred on the image (about 60% of its width), whatever its size."""
    height, width = image.shape[:2]
    font = cv2.FONT_HERSHEY_SIMPLEX
    (text_w, text_h), _ = cv2.getTextSize("PASS", font, 1.0, 1)
    scale = 0.6 * width / text_w
    if text_h * scale > 0.5 * height:
        scale = 0.5 * height / text_h
    thickness = max(2, round(scale * 2.5))
    (text_w, text_h), baseline = cv2.getTextSize("PASS", font, scale, thickness)
    origin = ((width - text_w) // 2, (height + text_h) // 2 - baseline - round(0.12 * text_h))
    cv2.putText(image, "PASS", origin, font, scale, (255, 0, 0), thickness, cv2.LINE_AA)


def _bgra_image(bgra: np.ndarray) -> QImage:
    return QImage(bgra.data, bgra.shape[1], bgra.shape[0], bgra.strides[0], QImage.Format.Format_RGB32)


class ImageCanvas(QWidget):
    """Shows the image fitted and handles zoom (wheel) and pan (drag) in place.
    Zoom is relative to fit, so swapping the preview for the full-resolution image moves nothing."""

    zoomStarted = Signal()
    zoomEnded = Signal()
    pointPicked = Signal(float, float)      # position in the shown image, 0..1 (pick mode)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setStyleSheet("background-color: #050505; border: none;")
        self._preview = None
        self._preview_buf = None
        self._full = None
        self._full_buf = None
        self._ratio = 1.0
        self.zoom = 1.0
        self.cx = 0.5
        self.cy = 0.5
        self._drag = None
        self._picking = False

    # ---- pick mode (grey / film-base pickers) ----
    def set_pick_mode(self, active: bool):
        self._picking = bool(active)
        if self._picking:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self._sync_cursor()

    def is_picking(self) -> bool:
        return self._picking

    def image_position(self, pos: QPointF):
        """Widget position -> (u, v) in the shown image (0..1), or None outside the image."""
        if self._preview is None:
            return None
        disp_w, disp_h = self._display_size()
        u = (pos.x() - (self.width() / 2 - self.cx * disp_w)) / disp_w
        v = (pos.y() - (self.height() / 2 - self.cy * disp_h)) / disp_h
        return (u, v) if 0.0 <= u <= 1.0 and 0.0 <= v <= 1.0 else None

    # ---- images ----
    def set_preview(self, rgb: np.ndarray):
        bgra = cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2BGRA)
        self._preview, self._preview_buf = _bgra_image(bgra), bgra
        self._full = self._full_buf = None   # new edits invalidate the old full-size image
        self._clamp()
        self.update()

    def set_full_bgra(self, bgra: np.ndarray):
        if self._preview is None or not self.is_zoomed():
            return
        self._full, self._full_buf = _bgra_image(bgra), bgra
        self.update()

    def set_full_ratio(self, ratio: float):
        self._ratio = max(1.0, float(ratio))

    def preview_width(self) -> int:
        return self._preview.width() if self._preview is not None else 0

    # ---- geometry ----
    def _aspect(self) -> float:
        return self._preview.width() / max(1, self._preview.height())

    def _display_size(self, zoom=None):
        aspect = self._aspect()
        width = fit_width(self.width(), self.height(), aspect) * (self.zoom if zoom is None else zoom)
        return width, width / aspect

    def _clamp(self):
        if self._preview is None:
            return
        disp_w, disp_h = self._display_size()
        self.cx, self.cy = clamp_center(self.width(), self.height(), disp_w, disp_h, self.cx, self.cy)

    def is_zoomed(self) -> bool:
        return self.zoom > 1.0 + 1e-6

    def full_width(self) -> float:
        if self._full is not None:
            return float(self._full.width())
        return self.preview_width() * self._ratio

    def zoom100(self) -> float:
        """Zoom value at which 1 image pixel = 1 screen pixel."""
        if self._preview is None:
            return 1.0
        fit = fit_width(self.width(), self.height(), self._aspect())
        return self.full_width() / self.devicePixelRatioF() / fit

    def max_zoom(self) -> float:
        return max(self.zoom100() * 3, 4.0)

    def zoom_at(self, pos: QPointF, new_zoom: float):
        if self._preview is None:
            return
        cw, ch = self.width(), self.height()
        old_w, old_h = self._display_size()
        px = (pos.x() - (cw / 2 - self.cx * old_w)) / old_w
        py = (pos.y() - (ch / 2 - self.cy * old_h)) / old_h
        was_zoomed = self.is_zoomed()
        new_zoom = min(max(new_zoom, 1.0), self.max_zoom())
        if new_zoom <= 1.0 + 1e-6:
            self.reset_fit()
            return
        new_w, new_h = self._display_size(new_zoom)
        self.zoom = new_zoom
        self.cx = px - (pos.x() - cw / 2) / new_w
        self.cy = py - (pos.y() - ch / 2) / new_h
        self._clamp()
        self._sync_cursor()
        self.update()
        if not was_zoomed:
            self.zoomStarted.emit()

    def zoom_to_100(self, anchor: QPointF | None = None):
        anchor = anchor or QPointF(self.width() / 2, self.height() / 2)
        self.zoom_at(anchor, max(self.zoom100(), 1.25))

    def reset_fit(self):
        if not self.is_zoomed():
            return
        self.zoom, self.cx, self.cy = 1.0, 0.5, 0.5
        self._full = self._full_buf = None
        self._drag = None
        self._sync_cursor()
        self.update()
        self.zoomEnded.emit()

    def _sync_cursor(self):
        if self._picking:
            self.setCursor(Qt.CursorShape.CrossCursor)
            return
        self.setCursor(Qt.CursorShape.OpenHandCursor if self.is_zoomed() else Qt.CursorShape.ArrowCursor)

    # ---- events ----
    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if not delta or self._preview is None:
            event.ignore()
            return
        self.zoom_at(event.position(), self.zoom * (1.0015 ** delta))
        event.accept()

    def mousePressEvent(self, event):
        if self._picking and event.button() == Qt.MouseButton.LeftButton:
            point = self.image_position(event.position())
            if point is not None:
                self.set_pick_mode(False)
                self.pointPicked.emit(*point)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self.is_zoomed():
            self._drag = (event.position(), self.cx, self.cy)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event):
        if self._drag is None:
            return
        start, cx, cy = self._drag
        disp_w, disp_h = self._display_size()
        self.cx = cx - (event.position().x() - start.x()) / disp_w
        self.cy = cy - (event.position().y() - start.y()) / disp_h
        self._clamp()
        self.update()

    def mouseReleaseEvent(self, event):
        if self._drag is not None:
            self._drag = None
            self._sync_cursor()
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if self.is_zoomed():
            self.reset_fit()
            event.accept()
        else:
            event.ignore()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._clamp()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#050505"))
        source = self._full if self._full is not None else self._preview
        if source is None:
            return
        cw, ch = self.width(), self.height()
        disp_w, disp_h = self._display_size()
        dpr = self.devicePixelRatioF()
        x0 = round((cw / 2 - self.cx * disp_w) * dpr) / dpr   # snapped to screen pixels
        y0 = round((ch / 2 - self.cy * disp_h) * dpr) / dpr
        left, top = max(0.0, x0), max(0.0, y0)
        right, bottom = min(float(cw), x0 + disp_w), min(float(ch), y0 + disp_h)
        if right <= left or bottom <= top:
            return
        sw, sh = source.width(), source.height()
        src = QRectF((left - x0) / disp_w * sw, (top - y0) / disp_h * sh,
                     (right - left) / disp_w * sw, (bottom - top) / disp_h * sh)
        # full image at >= 100% -> real pixels, no smoothing; otherwise (enlarged preview / downscale) -> smooth
        exact = source is self._full and disp_w * dpr / sw >= 1.0
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, not exact)
        painter.drawImage(QRectF(left, top, right - left, bottom - top), source, src)


class EnlargedView(QFrame):
    doubleClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.Box)
        self.setLineWidth(3)
        self.setStyleSheet("background-color: #0F1012; border: 3px solid #00E5FF;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        top_h = QHBoxLayout()
        self.lbl_id = QLabel("#01 (0°)")
        self.lbl_id.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.lbl_id.setStyleSheet("color: white; background: #1B1D1F; border: 1px solid #00E5FF; padding: 2px 8px; border-radius: 2px;")
        top_h.addWidget(self.lbl_id)

        top_h.addStretch()

        self.lbl_crop = QLabel("CROP:OFF")
        self.lbl_crop.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        self.lbl_crop.setStyleSheet("color: #00E5FF; background: #1B1D1F; border: 1px solid #00E5FF; padding: 2px 8px; border-radius: 2px;")
        top_h.addWidget(self.lbl_crop)
        layout.addLayout(top_h)

        self.canvas = ImageCanvas()
        layout.addWidget(self.canvas, stretch=1)

        bottom_h = QHBoxLayout()
        bottom_h.setSpacing(6)

        self.lbl_c = QLabel("C:+0")
        self.lbl_m = QLabel("M:+0")
        self.lbl_y = QLabel("Y:+0")
        self.lbl_d = QLabel("D:+0")
        for lbl in (self.lbl_c, self.lbl_m, self.lbl_y, self.lbl_d):
            lbl.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            lbl.setStyleSheet("color: #FFFFFF; background: #1A1D20; border: 2px solid #00E5FF; padding: 4px 12px;")
            bottom_h.addWidget(lbl, 1)

        self.lbl_status = QLabel("READY")
        self.lbl_status.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet("color: #00FF66; background: #1A1D20; border: 2px solid #00E5FF; padding: 4px 12px;")
        bottom_h.addWidget(self.lbl_status, 1)

        layout.addLayout(bottom_h)


    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)

    def update_view(self, item: FrameItem, rendered_rgb: np.ndarray):
        mirror_tag = " [M]" if item.mirror else ""
        self.lbl_id.setText(f"#{item.index + 1:02d} ({item.rotation}°){mirror_tag}")
        self.lbl_crop.setText("CROP:ON" if item.auto_crop else "CROP:OFF")

        self.lbl_c.setText(f"C:{item.cyan:+d}")
        self.lbl_m.setText(f"M:{item.magenta:+d}")
        self.lbl_y.setText(f"Y:{item.yellow:+d}")
        self.lbl_d.setText(f"D:{item.density:+d}")

        if item.is_passed:
            self.lbl_status.setText("PASS")
            self.lbl_status.setStyleSheet("color: #FF5252; background: #330000; border: 2px solid #FF5252; padding: 4px 12px;")
        else:
            self.lbl_status.setText("READY")
            self.lbl_status.setStyleSheet("color: #00FF66; background: #1A1D20; border: 2px solid #00E5FF; padding: 4px 12px;")

        disp = rendered_rgb
        if item.is_passed:
            disp = np.ascontiguousarray(rendered_rgb).copy()
            mark_passed(disp)
        self.canvas.set_preview(disp)
