#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Màn hình khởi động — logo trên nền đen, kín màn hình.

Nối tiếp psplash của hệ điều hành: psplash giữ logo trong lúc kernel và
systemd khởi động, màn này giữ đúng logo đó trong lúc app nạp artifact AI
(vài trăm ms tới hơn một giây). Không có nó thì giữa hai giai đoạn sẽ loé lên
một khoảng đen hoặc một cửa sổ trống — trông như máy vừa treo rồi bật lại.

Thiếu file logo cũng không sao: vẫn hiện chữ trên nền đen, app không bao giờ
chết chỉ vì thiếu một tấm ảnh.
"""

import time
import os

from PyQt5.QtCore import Qt, QTimer, QRectF
from PyQt5.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt5.QtWidgets import QWidget

# Nền đen tuyệt đối, không phải màu nền của app: liền mạch với psplash và với
# lúc màn hình chưa sáng.
BACKGROUND = "#000000"
LOGO_MAX_RATIO = 0.34        # cạnh logo tối đa so với cạnh ngắn của màn hình

BAR_COLOR = "#38bdf8"
BAR_TRACK = "#1e2836"
BAR_WIDTH_RATIO = 0.30       # bề ngang thanh so với bề ngang màn hình
BAR_HEIGHT = 6

# Thanh bò tới mức này rồi dừng chờ; chỉ chạy nốt khi thật sự nạp xong. Một
# thanh chạy đầy 100% rồi vẫn đứng đó là lời nói dối mà ai cũng nhận ra.
CREEP_CEILING = 0.92
DEFAULT_FILL_MS = 2200

SEARCH_PATHS = [
    os.environ.get("HMI_LOGO"),
    "/usr/share/hmi-app/logo.png",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "assets", "logo.png"),
]


def find_logo():
    for path in SEARCH_PATHS:
        if path and os.path.exists(path):
            return path
    return None


class SplashScreen(QWidget):
    """Cửa sổ khởi động: logo giữa màn, một dòng trạng thái nhỏ bên dưới."""

    def __init__(self, title="", subtitle="Đang khởi động…",
                 fill_ms=DEFAULT_FILL_MS, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setStyleSheet(f"background-color: {BACKGROUND};")
        self.title = title
        self.subtitle = subtitle

        self._pixmap = None
        path = find_logo()
        if path:
            pm = QPixmap(path)
            if not pm.isNull():
                self._pixmap = pm

        # Thanh nạp: _target là mức muốn tới, _value là mức đang vẽ. Tách hai
        # biến để thanh trượt mượt tới đích thay vì nhảy giật từng nấc.
        self._value = 0.0
        self._target = 0.0
        self._fill_ms = max(1, int(fill_ms))
        self._t0 = time.monotonic()
        self._anim = QTimer(self)
        self._anim.timeout.connect(self._tick)
        self._anim.start(33)                 # ~30 khung/giây, đủ mượt, rẻ

    def _tick(self):
        # Tự bò theo thời gian để thanh không bao giờ đứng im (người nhìn một
        # thanh bất động 2 giây sẽ tưởng máy treo), nhưng chỉ tới CREEP_CEILING.
        elapsed = (time.monotonic() - self._t0) * 1000.0
        creep = min(CREEP_CEILING, elapsed / self._fill_ms)
        target = max(self._target, creep)
        if abs(target - self._value) < 0.001:
            self._value = target
            return
        self._value += (target - self._value) * 0.18
        self.update()

    def set_progress(self, value):
        """0..1. Gọi 1.0 khi thật sự xong — thanh mới chạy nốt tới cuối."""
        self._target = max(0.0, min(1.0, float(value)))

    def set_status(self, text, progress=None):
        self.subtitle = text
        if progress is not None:
            self.set_progress(progress)
        self.repaint()          # đang chặn vòng sự kiện, update() sẽ không kịp vẽ

    # ------------------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(BACKGROUND))

        y = h // 2
        if self._pixmap is not None:
            side = int(min(w, h) * LOGO_MAX_RATIO)
            pm = self._pixmap.scaled(side, side, Qt.KeepAspectRatio,
                                     Qt.SmoothTransformation)
            x = (w - pm.width()) // 2
            top = (h - pm.height()) // 2 - int(h * 0.06)
            p.drawPixmap(x, top, pm)
            y = top + pm.height()
        else:
            f = QFont(); f.setPointSize(34); f.setBold(True)
            p.setFont(f)
            p.setPen(QColor("#1a4f9c"))
            p.drawText(0, 0, w, h - int(h * 0.10), Qt.AlignCenter, "BK TP.HCM")
            y = h // 2 + int(h * 0.05)

        if self.title:
            f = QFont(); f.setPointSize(15); f.setBold(True)
            p.setFont(f)
            p.setPen(QColor("#e6edf3"))
            p.drawText(0, y + 18, w, 34, Qt.AlignHCenter | Qt.AlignTop, self.title)
            y += 40

        # --- thanh nạp ---
        bar_w = int(w * BAR_WIDTH_RATIO)
        bar_x = (w - bar_w) / 2.0
        bar_y = y + 26
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(BAR_TRACK))
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, BAR_HEIGHT),
                          BAR_HEIGHT / 2, BAR_HEIGHT / 2)
        filled = bar_w * self._value
        if filled > 1.0:
            p.setBrush(QColor(BAR_COLOR))
            p.drawRoundedRect(QRectF(bar_x, bar_y, filled, BAR_HEIGHT),
                              BAR_HEIGHT / 2, BAR_HEIGHT / 2)

        f = QFont(); f.setPointSize(10)
        p.setFont(f)
        p.setPen(QColor("#7d8da1"))
        p.drawText(0, bar_y + BAR_HEIGHT + 12, w, 28,
                   Qt.AlignHCenter | Qt.AlignTop, self.subtitle)
        p.end()


__all__ = ["SplashScreen", "find_logo"]
