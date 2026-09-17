from __future__ import annotations

from typing import Optional, Tuple

import cv2
import numpy as np

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import (
    QColor, QFont, QImage, QPainter, QPen, QPixmap,
)
from PySide6.QtWidgets import QLabel


class CameraPreviewLabel(QLabel):
    watch_window_drawn      = Signal(QRect)
    watch_window_draw_state = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        self.pixmap: Optional[QPixmap] = None
        self.overlay_rect: Optional[QRect] = None

        # Watch-window draw state
        self.selection_mode: bool          = False
        self.drawing:        bool          = False
        self.start_point:    Optional[QPoint] = None
        self.end_point:      Optional[QPoint] = None
        self.locked_aspect_ratio: Optional[float] = None

        self._hud_visible:     bool  = False
        self._hud_fps:         float = 0.0
        self._hud_dropped:     int   = 0
        self._hud_disconnects: int   = 0
        self._hud_watch:       str   = ""

        self._exposure_overlay: bool                  = False
        self._exp_over_mask:    Optional[np.ndarray]  = None   # uint8 bool mask (H, W)
        self._exp_under_mask:   Optional[np.ndarray]  = None

        self._watch_origin: QPoint = QPoint(0, 0)

        # Watch rect visual overlay (full-sensor coords, visual-only — NOT sent to camera)
        self._watch_rect:        Optional[QRect]  = None
        self._watch_drag_handle: Optional[int]    = None  # handle index (0-7) or None=body
        self._watch_drag_start:  Optional[QPoint] = None  # label coord where drag began
        self._watch_drag_snap:   Optional[QRect]  = None  # _watch_rect at drag start

        # Zoom / pan state
        self._zoom: float        = 1.0
        self._pan:  QPoint       = QPoint(0, 0)
        self._pan_start:  Optional[QPoint] = None
        self._pan_origin: QPoint = QPoint(0, 0)


    def setPixmap(self, pixmap: QPixmap) -> None:
        self.pixmap = pixmap
        self.update()

    def set_overlay(self, rect: QRect) -> None:
        self.overlay_rect = rect
        self.update()

    def set_hud_visible(self, visible: bool) -> None:
        self._hud_visible = visible
        self.update()

    def update_hud(self, fps: float, dropped: int, disconnects: int) -> None:
        self._hud_fps         = fps
        self._hud_dropped     = dropped
        self._hud_disconnects = disconnects
        self.update()

    def set_watch_text(self, text: str) -> None:
        self._hud_watch = text
        self.update()

    def set_watch_origin(self, origin: QPoint) -> None:
        """Record the full-sensor offset of the current watch window."""
        self._watch_origin = origin

    def get_watch_rect(self) -> Optional[QRect]:
        return self._watch_rect

    def set_watch_rect(self, rect: Optional[QRect]) -> None:
        """Display a watch-window reference overlay in full-sensor coordinates.

        The rect is shown with handles for interactive move/resize.  It is purely
        visual — no camera command is issued.  Pass None to hide the overlay.
        """
        self._watch_rect = rect if (rect and not rect.isNull()) else None
        self.update()

    def clear_watch_rect(self) -> None:
        """Remove the watch-window overlay and emit watch_window_drawn(QRect())."""
        self._watch_rect = None
        self._watch_drag_handle = None
        self._watch_drag_start  = None
        self._watch_drag_snap   = None
        self.watch_window_drawn.emit(QRect())
        self.update()

    def set_exposure_overlay(self, enabled: bool) -> None:
        self._exposure_overlay = enabled
        if not enabled:
            self._exp_over_mask = self._exp_under_mask = None
        self.update()

    def update_exposure_overlay(self, frame: np.ndarray) -> None:
        """Recompute over/under masks from a BGR or grayscale frame."""
        if not self._exposure_overlay:
            return
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        self._exp_over_mask  = (gray >= 250).astype(np.uint8)
        self._exp_under_mask = (gray <= 5).astype(np.uint8)
        self.update()


    def begin_watch_selection(self, aspect_ratio: Optional[float]) -> None:
        self.selection_mode       = True
        self.locked_aspect_ratio  = aspect_ratio
        self.drawing              = False
        self.start_point          = None
        self.end_point            = None
        self.set_overlay(QRect())
        self.setCursor(Qt.CursorShape.CrossCursor)


    def mousePressEvent(self, event) -> None:
        pos = event.position().toPoint()

        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_start  = pos
            self._pan_origin = QPoint(self._pan)
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self._watch_rect is not None and not self.selection_mode:
            handle = self._watch_hit_handle(pos)
            lr = self._watch_rect_label()
            if handle is not None or lr.contains(pos):
                self._watch_drag_handle = handle  # None means body drag
                self._watch_drag_start  = pos
                self._watch_drag_snap   = QRect(self._watch_rect)
                return

        if self.selection_mode:
            self.start_point = pos
            self.end_point   = pos
            self.drawing     = True
            self.watch_window_draw_state.emit("Drawing")

    def mouseMoveEvent(self, event) -> None:
        pos = event.position().toPoint()

        if event.buttons() & Qt.MouseButton.MiddleButton and self._pan_start is not None:
            delta = pos - self._pan_start
            self._pan = self._pan_origin + delta
            self.update()
            return

        if self._watch_drag_start is not None and self._watch_drag_snap is not None:
            self._apply_watch_drag(pos)
            self.update()
            return

        if not self.drawing or not self.start_point:
            return

        self.end_point = pos
        rect = QRect(self.start_point, pos).normalized()

        if self.selection_mode and self.locked_aspect_ratio:
            rect.setHeight(int(rect.width() / self.locked_aspect_ratio))

        self.overlay_rect = rect
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        pos = event.position().toPoint()

        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_start = None
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self._watch_drag_start is not None:
            self._watch_drag_handle = None
            self._watch_drag_start  = None
            self._watch_drag_snap   = None
            if self._watch_rect is not None:
                self.watch_window_drawn.emit(self._watch_rect)
            self.update()
            return

        if not self.drawing:
            return

        self.drawing = False
        if not (self.start_point and self.end_point):
            return

        rect = QRect(self.start_point, self.end_point).normalized()

        if self.selection_mode:
            if self.locked_aspect_ratio:
                rect.setHeight(int(rect.width() / self.locked_aspect_ratio))
            # Use unclamped corner conversion (no intersected() clamp) so the
            # stored rect reflects exactly where the user drew, not the nearest
            # image boundary.  _label_pt_to_frame_pt converts without clamping.
            frame_rect = self._label_rect_to_frame_rect_unclamped(rect)
            self.selection_mode = False
            self.watch_window_draw_state.emit("Idle")
            self._watch_rect = frame_rect if (frame_rect and not frame_rect.isEmpty()) else None
            self.watch_window_drawn.emit(frame_rect if self._watch_rect else QRect())
            self.set_overlay(QRect())
            self.unsetCursor()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._zoom = 1.0
            self._pan  = QPoint(0, 0)
            self.update()

    def wheelEvent(self, event) -> None:
        if self.pixmap is None:
            return
        factor   = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        old_zoom = self._zoom
        new_zoom = max(1.0, min(self._zoom * factor, 20.0))
        if new_zoom == old_zoom:
            return

        if new_zoom == 1.0:
            self._pan = QPoint(0, 0)
        else:
            cursor = event.position().toPoint()
            dw, dh, ox, oy = self._img_params()
            if dw > 0 and dh > 0:
                fx = (cursor.x() - ox) / dw
                fy = (cursor.y() - oy) / dh
            else:
                fx, fy = 0.5, 0.5

            pw, ph = self.pixmap.width(), self.pixmap.height()
            ww, wh = self.width(), self.height()
            scale = min(ww / pw, wh / ph) if pw > 0 and ph > 0 else 1.0
            fit_w = int(pw * scale)
            fit_h = int(ph * scale)
            new_dw = int(fit_w * new_zoom)
            new_dh = int(fit_h * new_zoom)
            new_ox = cursor.x() - fx * new_dw
            new_oy = cursor.y() - fy * new_dh
            self._pan = QPoint(
                int(new_ox - (ww - new_dw) // 2),
                int(new_oy - (wh - new_dh) // 2),
            )

        self._zoom = new_zoom
        self.update()


    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        hud_anchor_x, hud_anchor_y = 0, 0

        if self.pixmap and self.pixmap.width() > 0:
            dw, dh, ox, oy = self._img_params()
            if dw > 0 and dh > 0:
                dest_x = max(0, ox)
                dest_y = max(0, oy)
                dest_r = min(self.width(),  ox + dw)
                dest_b = min(self.height(), oy + dh)
                dest_w = dest_r - dest_x
                dest_h = dest_b - dest_y
                if dest_w > 0 and dest_h > 0:
                    pw = self.pixmap.width()
                    ph = self.pixmap.height()
                    sx = pw / dw
                    sy = ph / dh
                    src = QRect(
                        int((dest_x - ox) * sx),
                        int((dest_y - oy) * sy),
                        int(dest_w * sx),
                        int(dest_h * sy),
                    )
                    painter.drawPixmap(QRect(dest_x, dest_y, dest_w, dest_h),
                                       self.pixmap, src)

            hud_anchor_x = max(0, ox)
            hud_anchor_y = max(0, oy)

        if (self._exposure_overlay
                and self.pixmap and self.pixmap.width() > 0
                and (self._exp_over_mask is not None or self._exp_under_mask is not None)):
            dw, dh, ox, oy = self._img_params()

            if dw > 0 and dh > 0:
                for mask, r, g, b, a in (
                    (self._exp_over_mask,  220, 30, 30, 140),   # red — overexposed
                    (self._exp_under_mask, 30, 80, 220, 140),   # blue — underexposed
                ):
                    if mask is None:
                        continue
                    disp = cv2.resize(mask, (dw, dh), interpolation=cv2.INTER_NEAREST)
                    rgba = np.zeros((dh, dw, 4), dtype=np.uint8)
                    rgba[disp > 0] = [r, g, b, a]
                    qi = QImage(
                        rgba.data, dw, dh, dw * 4,
                        QImage.Format.Format_RGBA8888,
                    )
                    painter.drawImage(QPoint(ox, oy), qi)

        if self._hud_visible:
            font = QFont("Courier New", 9)
            painter.setFont(font)
            fm = painter.fontMetrics()

            lines = [
                f"FPS  {self._hud_fps:5.1f}",
                f"DROP {self._hud_dropped}",
                f"DISC {self._hud_disconnects}",
                f"WW   {self._hud_watch}" if self._hud_watch else "WW   full sensor",
            ]

            max_w  = max(fm.horizontalAdvance(line) for line in lines)
            line_h = fm.height()
            pad    = 6
            hud_w  = max_w + pad * 2
            hud_h  = line_h * len(lines) + pad * 2
            margin = 10

            painter.fillRect(
                QRect(hud_anchor_x + margin, hud_anchor_y + margin, hud_w, hud_h),
                QColor(0, 0, 0, 170),
            )
            painter.setPen(QColor(0, 230, 0))
            for i, line in enumerate(lines):
                y = hud_anchor_y + margin + pad + fm.ascent() + line_h * i
                painter.drawText(hud_anchor_x + margin + pad, y, line)

        if self.overlay_rect is not None and not self.overlay_rect.isNull():
            pen = QPen(QColor(0, 255, 0), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(self.overlay_rect)

        if self._watch_rect is not None and not self._watch_rect.isNull() and self.pixmap:
            lr = self._watch_rect_label()
            if not lr.isNull():
                painter.setPen(QPen(QColor(0, 255, 80), 2, Qt.PenStyle.SolidLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(lr)
                # Draw 8 resize handles
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0, 230, 80))
                for hpt in self._watch_handle_pts(lr):
                    painter.drawRect(hpt.x() - 4, hpt.y() - 4, 8, 8)

        painter.end()


    def _label_rect_to_frame_rect_unclamped(self, rect: QRect) -> QRect:
        """Convert a label rect to full-sensor coords WITHOUT clamping to image bounds.

        Unlike a clamped conversion (which intersects with the image area first),
        this converts corners directly so the result preserves the drawn position even
        when the rubber-band starts in the letterbox area.
        """
        if not self.pixmap:
            return QRect()
        dw, dh, ox, oy = self._img_params()
        if dw == 0 or dh == 0:
            return QRect()
        sx = self.pixmap.width()  / dw
        sy = self.pixmap.height() / dh
        return QRect(
            int((rect.x()      - ox) * sx) + self._watch_origin.x(),
            int((rect.y()      - oy) * sy) + self._watch_origin.y(),
            int(rect.width()         * sx),
            int(rect.height()        * sy),
        )

    def _img_params(self) -> Tuple[int, int, int, int]:
        """Return (display_w, display_h, origin_x, origin_y) for current zoom/pan."""
        if not self.pixmap:
            return 0, 0, 0, 0
        pw, ph = self.pixmap.width(), self.pixmap.height()
        if pw == 0 or ph == 0:
            return 0, 0, 0, 0
        ww, wh = self.width(), self.height()
        scale = min(ww / pw, wh / ph)
        fit_w = int(pw * scale)
        fit_h = int(ph * scale)
        dw = int(fit_w * self._zoom)
        dh = int(fit_h * self._zoom)
        ox = (ww - dw) // 2 + self._pan.x()
        oy = (wh - dh) // 2 + self._pan.y()
        return dw, dh, ox, oy

    def _frame_rect_to_label_rect(self, rect: QRect) -> QRect:
        """Convert a pixmap (watch-window-relative) rectangle to label coordinates."""
        if not self.pixmap:
            return QRect()
        dw, dh, ox, oy = self._img_params()
        if dw == 0 or dh == 0:
            return QRect()
        pw = self.pixmap.width()
        ph = self.pixmap.height()
        sx = dw / pw
        sy = dh / ph
        return QRect(
            int(rect.x() * sx) + ox,
            int(rect.y() * sy) + oy,
            int(rect.width()  * sx),
            int(rect.height() * sy),
        )


    def _watch_rect_label(self) -> QRect:
        """Return _watch_rect converted to label (widget) coordinates."""
        if self._watch_rect is None or self._watch_rect.isNull() or not self.pixmap:
            return QRect()
        pixmap_rect = QRect(
            self._watch_rect.x() - self._watch_origin.x(),
            self._watch_rect.y() - self._watch_origin.y(),
            self._watch_rect.width(), self._watch_rect.height(),
        )
        return self._frame_rect_to_label_rect(pixmap_rect)

    def _watch_handle_pts(self, lr: QRect) -> list[QPoint]:
        """8 handle positions (TL TC TR ML MR BL BC BR) for a label rect."""
        cx = lr.center().x()
        cy = lr.center().y()
        return [
            lr.topLeft(),                    QPoint(cx, lr.top()),    lr.topRight(),
            QPoint(lr.left(), cy),                                     QPoint(lr.right(), cy),
            lr.bottomLeft(),                 QPoint(cx, lr.bottom()), lr.bottomRight(),
        ]

    def _watch_hit_handle(self, pos: QPoint) -> Optional[int]:
        """Return handle index (0-7) if pos is within hit radius, else None."""
        lr = self._watch_rect_label()
        if lr.isNull():
            return None
        for i, hpt in enumerate(self._watch_handle_pts(lr)):
            if abs(pos.x() - hpt.x()) <= 8 and abs(pos.y() - hpt.y()) <= 8:
                return i
        return None

    def _apply_watch_drag(self, pos: QPoint) -> None:
        """Update _watch_rect based on current drag position."""
        if self._watch_drag_snap is None or self._watch_drag_start is None:
            return

        dw, dh, _, _ = self._img_params()

        if not self.pixmap or dw == 0 or dh == 0:
            return

        sx = self.pixmap.width()  / dw
        sy = self.pixmap.height() / dh
        delta = pos - self._watch_drag_start
        dx = int(delta.x() * sx)
        dy = int(delta.y() * sy)

        snap = self._watch_drag_snap
        x0, y0, w0, h0 = snap.x(), snap.y(), snap.width(), snap.height()

        h = self._watch_drag_handle

        if h is None:
            self._watch_rect = QRect(x0 + dx, y0 + dy, w0, h0)
        else:
            left, top, right, bot = x0, y0, x0 + w0, y0 + h0
            if h in (0, 3, 5):   left  = min(x0 + dx, right - 4)
            if h in (2, 4, 7):   right = max(x0 + w0 + dx, left + 4)
            if h in (0, 1, 2):   top   = min(y0 + dy, bot  - 4)
            if h in (5, 6, 7):   bot   = max(y0 + h0 + dy, top  + 4)
            self._watch_rect = QRect(left, top, right - left, bot - top)
