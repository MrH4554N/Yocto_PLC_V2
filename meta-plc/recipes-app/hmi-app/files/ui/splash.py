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

import os

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt5.QtWidgets import QWidget

# Nền đen tuyệt đối, không phải màu nền của app: liền mạch với psplash và với
# lúc màn hình chưa sáng.
BACKGROUND = "#000000"
LOGO_MAX_RATIO = 0.34        # cạnh logo tối đa so với cạnh ngắn của màn hình

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

    def __init__(self, title="", subtitle="Đang khởi động…", parent=None):
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

    def set_status(self, text):
        self.subtitle = text
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

        f = QFont(); f.setPointSize(10)
        p.setFont(f)
        p.setPen(QColor("#7d8da1"))
        p.drawText(0, y + 20, w, 28, Qt.AlignHCenter | Qt.AlignTop, self.subtitle)
        p.end()


__all__ = ["SplashScreen", "find_logo"]
