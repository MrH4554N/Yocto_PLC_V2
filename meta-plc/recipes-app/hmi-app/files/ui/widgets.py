#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Widget dùng chung giữa các trang.

Sparkline và thanh envelope vẽ thẳng bằng QPainter thay vì pyqtgraph: mỗi thẻ
số chỉ cần một đường 120 điểm không trục, mà một PlotWidget kéo theo cả bộ máy
scene/view của pyqtgraph — bốn cái chạy 2 Hz là quá nhiều cho Pi 4. pyqtgraph
vẫn dùng ở trang Đồ thị, nơi thật sự cần trục và lưới.
"""

import time
from collections import deque

from PyQt5.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter,
                         QPainterPath, QPen)
from PyQt5.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                             QSizePolicy, QVBoxLayout, QWidget)
import pyqtgraph as pg

from ui.theme import C, MONO


# ==========================================================================
# SPARKLINE
# ==========================================================================
class Sparkline(QWidget):
    """Đường xu hướng nhỏ, không trục, có nền chuyển sắc dưới đường.

    Giữ dữ liệu theo THỜI GIAN (mặc định 120 giây gần nhất) chứ không theo số
    mẫu. Đây chính là chỗ đồ thị cũ sai: nó nhồi mọi mẫu từ lúc khởi động vào
    một khung cố định, nên càng chạy lâu đường càng bị nén cho tới khi thành
    một vệt răng cưa vô nghĩa.
    """

    def __init__(self, color, window_s=120.0, min_span=0.0, parent=None):
        super().__init__(parent)
        self.color = QColor(color)
        self.window_s = float(window_s)
        # Biên độ TỐI THIỂU của trục đứng. Không có nó thì khi tín hiệu gần
        # như đứng yên (điện áp 0,0-0,1 V lúc máy tắt), trục tự co lại đúng
        # bằng dải nhiễu và một dao động 0,05 V bị phóng lên full khung —
        # nhìn như máy đang giật đùng đùng trong khi nó đang nằm im.
        self.min_span = float(min_span)
        self._pts = deque()          # (ts, value)
        self.setMinimumHeight(46)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def add(self, value, ts=None):
        ts = time.monotonic() if ts is None else float(ts)
        self._pts.append((ts, float(value)))
        cutoff = ts - self.window_s
        while self._pts and self._pts[0][0] < cutoff:
            self._pts.popleft()
        self.update()

    def clear(self):
        self._pts.clear()
        self.update()

    def paintEvent(self, event):
        if len(self._pts) < 2:
            return
        w, h = self.width(), self.height()
        pad = 3.0

        ts = [p[0] for p in self._pts]
        vs = [p[1] for p in self._pts]
        t0, t1 = ts[0], ts[-1]
        tspan = max(t1 - t0, 1e-6)

        vmin, vmax = min(vs), max(vs)
        vspan = max(vmax - vmin, self.min_span, 1e-9)
        mid = (vmax + vmin) / 2.0
        vmin, vmax = mid - vspan / 2.0, mid + vspan / 2.0

        def xy(t, v):
            x = (t - t0) / tspan * (w - 2 * pad) + pad
            y = h - pad - (v - vmin) / vspan * (h - 2 * pad)
            return QPointF(x, y)

        path = QPainterPath()
        path.moveTo(xy(ts[0], vs[0]))
        for t, v in zip(ts[1:], vs[1:]):
            path.lineTo(xy(t, v))

        fill = QPainterPath(path)
        fill.lineTo(QPointF(w - pad, h))
        fill.lineTo(QPointF(pad, h))
        fill.closeSubpath()

        grad = QLinearGradient(0, 0, 0, h)
        top = QColor(self.color); top.setAlpha(70)
        bot = QColor(self.color); bot.setAlpha(0)
        grad.setColorAt(0.0, top)
        grad.setColorAt(1.0, bot)

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillPath(fill, QBrush(grad))
        p.setPen(QPen(self.color, 2.0))
        p.drawPath(path)
        p.end()


# ==========================================================================
# THẺ SỐ LIỆU
# ==========================================================================
class MetricCard(QFrame):
    """Thẻ KPI: nhãn — giá trị lớn + đơn vị — dòng phụ — sparkline."""

    def __init__(self, title, unit, color, fmt="{:.1f}", min_span=0.0,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.fmt = fmt
        self.color = color

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 10)
        lay.setSpacing(2)

        self.lbl_title = QLabel(title.upper())
        self.lbl_title.setObjectName("CardTitle")

        row = QHBoxLayout()
        row.setSpacing(5)
        row.setContentsMargins(0, 0, 0, 0)
        self.lbl_value = QLabel("--")
        self.lbl_value.setStyleSheet(
            f"font-family: {MONO}; font-size: 33px; font-weight: 800; color: {color};")
        self.lbl_unit = QLabel(unit)
        self.lbl_unit.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {C['muted']};")
        row.addWidget(self.lbl_value)
        row.addWidget(self.lbl_unit, alignment=Qt.AlignBottom)
        row.addStretch()

        self.lbl_sub = QLabel(" ")
        self.lbl_sub.setObjectName("CardSub")

        self.spark = Sparkline(color, min_span=min_span)

        lay.addWidget(self.lbl_title)
        lay.addLayout(row)
        lay.addWidget(self.lbl_sub)
        lay.addSpacing(2)
        lay.addWidget(self.spark, stretch=1)

    def set_value(self, value, sub=None, ts=None):
        self.lbl_value.setText(self.fmt.format(value))
        if sub is not None:
            self.lbl_sub.setText(sub)
        self.spark.add(value, ts=ts)

    def set_stale(self):
        """Mất nguồn dữ liệu: nói thẳng là không có số, không giữ số cũ."""
        self.lbl_value.setText("--")
        self.lbl_sub.setText("mất dữ liệu")


# ==========================================================================
# THANH ENVELOPE
# ==========================================================================
class BarMeter(QWidget):
    """Thanh mức có vạch giới hạn: giá trị / dải cho phép.

    Đổi màu khi vượt ngưỡng cảnh báo — nhìn thanh là biết còn bao nhiêu dư địa,
    thứ mà một con số trần không nói được.
    """

    def __init__(self, label, unit, color, vmin=0.0, vmax=100.0,
                 warn_at=None, fmt="{:.1f}", parent=None):
        super().__init__(parent)
        self.label, self.unit, self.fmt = label, unit, fmt
        self.color = QColor(color)
        self.vmin, self.vmax = float(vmin), float(vmax)
        self.warn_at = warn_at
        self.value = None
        self.setMinimumHeight(46)

    def set_value(self, value):
        self.value = None if value is None else float(value)
        self.update()

    def set_range(self, vmin, vmax):
        self.vmin, self.vmax = float(vmin), float(vmax)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        bar_h = 9
        bar_y = h - bar_h - 2

        f = QFont(); f.setPointSize(11); f.setBold(True)
        p.setFont(f)
        txt = "--" if self.value is None else self.fmt.format(self.value)
        over = (self.warn_at is not None and self.value is not None
                and self.value >= self.warn_at)
        p.setPen(QColor(C["err"] if over else self.color.name()))
        p.drawText(QRectF(0, 0, w, 20), Qt.AlignLeft | Qt.AlignVCenter, f"{txt} {self.unit}")

        f2 = QFont(); f2.setPointSize(8)
        p.setFont(f2)
        p.setPen(QColor(C["dim"]))
        p.drawText(QRectF(0, 0, w, 20), Qt.AlignRight | Qt.AlignVCenter,
                   f"{self.label}   {self.fmt.format(self.vmin)}–{self.fmt.format(self.vmax)}")

        # rãnh
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(C["panel2"]))
        p.drawRoundedRect(QRectF(0, bar_y, w, bar_h), 4, 4)

        # mức
        if self.value is not None and self.vmax > self.vmin:
            frac = (self.value - self.vmin) / (self.vmax - self.vmin)
            frac = max(0.0, min(1.0, frac))
            p.setBrush(QColor(C["err"]) if over else self.color)
            p.drawRoundedRect(QRectF(0, bar_y, max(w * frac, 4.0), bar_h), 4, 4)

        # vạch ngưỡng
        if self.warn_at is not None and self.vmax > self.vmin:
            wf = (float(self.warn_at) - self.vmin) / (self.vmax - self.vmin)
            if 0.0 <= wf <= 1.0:
                x = w * wf
                p.setPen(QPen(QColor(C["err"]), 2))
                p.drawLine(QPointF(x, bar_y - 3), QPointF(x, bar_y + bar_h + 3))
        p.end()


# ==========================================================================
# TRẠNG THÁI
# ==========================================================================
class StatusDot(QWidget):
    """Chấm tròn + nhãn: PLC / INA219 / AI trên header."""

    COLORS = {"ok": C["ok"], "warn": C["warn"], "err": C["err"], "off": C["dim"]}

    def __init__(self, text, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self._dot = QLabel()
        self._dot.setFixedSize(9, 9)
        self._dot.setStyleSheet(
            f"background-color: {C['dim']}; border-radius: 4px;")
        self._txt = QLabel(text)
        self._txt.setStyleSheet(f"color: {C['muted']}; font-size: 12px; font-weight: 700;")
        lay.addWidget(self._dot)
        lay.addWidget(self._txt)

    def set_state(self, state):
        self._dot.setStyleSheet(
            f"background-color: {self.COLORS.get(state, C['dim'])};"
            f"border-radius: 4px;")


class StatusPill(QLabel):
    """Nhãn trạng thái dạng viên thuốc."""

    STYLES = {
        "ok":   (C["ok"],   "#0c2a1f"),
        "warn": (C["warn"], "#2c2410"),
        "err":  (C["err"],  "#2d1416"),
        "info": (C["info"], "#0c2333"),
        "off":  (C["dim"],  C["panel2"]),
    }

    def __init__(self, text="--", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.set_state("off", text)

    def set_state(self, state, text=None):
        fg, bg = self.STYLES.get(state, self.STYLES["off"])
        if text is not None:
            self.setText(text)
        self.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border-radius: 10px;"
            f"padding: 4px 11px; font-size: 11px; font-weight: 800;")


# ==========================================================================
# MỘT DÒNG CẢNH BÁO
# ==========================================================================
class AlertRow(QFrame):
    """Một mục trong danh sách cảnh báo: vạch màu | tiêu đề + mô tả | giờ."""


    def __init__(self, alert, compact=False, fade=0.0, parent=None):
        """compact=True: mô tả rút về một dòng. fade: 0 = rõ, 1 = sắp biến mất.

        Thẻ tóm tắt ở trang Giám sát có chiều cao cố định; để mô tả nhiều dòng
        tự do ở đó thì hàng cảnh báo sẽ đẩy cả trang cao lên và tràn khỏi màn
        1024×600.

        Việc mờ dần không phải để đẹp: nó cho biết dòng này SẮP tự biến mất,
        nên người vận hành không đi tìm nút xoá và cũng không tưởng hệ thống
        vừa quên mất một cảnh báo.
        """
        super().__init__(parent)
        self.setObjectName("Sunken")
        kind = "resolved" if alert.resolved_ts else alert.severity
        color = _blend({"critical": C["err"], "warning": C["warn"],
                        "info": C["info"], "resolved": C["ok"]}[kind],
                       C["panel"], fade)
        text_color = _blend(C["text"], C["panel"], fade)
        sub_color = _blend(C["dim"], C["panel"], fade)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(10)

        # Ô màu vẽ bằng stylesheet, KHÔNG dùng ký tự: image Yocto không cài
        # font nào có bộ Dingbats, nên ✓ ✕ hiện ra thành ô vuông rỗng trên
        # máy thật. Màu đã đủ phân biệt mức nghiêm trọng.
        icon = QLabel()
        icon.setFixedSize(10, 10)
        icon.setStyleSheet(
            f"background-color: {color}; border-radius: 5px;")

        mid = QVBoxLayout()
        mid.setSpacing(1)
        title = QLabel(alert.title)
        title.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {text_color};")
        title.setWordWrap(not compact)
        mid.addWidget(title)
        if alert.detail:
            text = alert.detail.split("\n")[0] if compact else alert.detail
            det = QLabel(text)
            det.setStyleSheet(
                f"font-family: {MONO}; font-size: 11px; color: {sub_color};")
            det.setWordWrap(not compact)
            mid.addWidget(det)

        stamp = QLabel(time.strftime("%H:%M:%S", time.localtime(
            alert.resolved_ts or alert.ts)))
        stamp.setStyleSheet(
            f"font-family: {MONO}; font-size: 11px; color: {sub_color};")
        stamp.setAlignment(Qt.AlignTop | Qt.AlignRight)

        lay.addWidget(icon, alignment=Qt.AlignTop)
        lay.addLayout(mid, stretch=1)
        lay.addWidget(stamp, alignment=Qt.AlignTop)


# ==========================================================================
# THANH ĐIỀU HƯỚNG DƯỚI
# ==========================================================================
class NavBar(QFrame):
    """Thanh tab dưới cùng, mỗi tab một glyph + nhãn, có badge số cảnh báo."""

    switched = pyqtSignal(int)

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.setObjectName("NavBar")
        self.setFixedHeight(66)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.buttons = []
        self._badges = {}
        for i, (glyph, label) in enumerate(items):
            # Bỏ glyph: font trên image thiếu ký tự, chúng hiện ra ô vuông.
            btn = QPushButton(label)
            btn.setObjectName("NavBtn")
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.clicked.connect(lambda _, idx=i: self.select(idx))
            lay.addWidget(btn, stretch=1)
            self.buttons.append(btn)

    def select(self, idx):
        for i, b in enumerate(self.buttons):
            b.setChecked(i == idx)
        self.switched.emit(idx)

    def set_badge(self, idx, count):
        """Đánh dấu tab có việc chưa xử lý bằng dấu chấm trong nhãn."""
        btn = self.buttons[idx]
        label = btn.text().split("  •")[0]
        btn.setText(label + ("  •" if count else ""))


def _blend(color, background, ratio):
    """Trộn màu về phía nền theo tỉ lệ 0..1 — cách làm mờ rẻ nhất.

    Dùng phép trộn màu thay vì QGraphicsOpacityEffect: hiệu ứng opacity của Qt
    bắt widget vẽ qua một lớp đệm riêng, tốn hơn hẳn trên Pi 4 mà kết quả nhìn
    y hệt trên nền phẳng một màu như thế này.
    """
    ratio = max(0.0, min(1.0, float(ratio)))
    if ratio <= 0.0:
        return color
    c, b = QColor(color), QColor(background)
    return QColor(
        int(c.red() + (b.red() - c.red()) * ratio),
        int(c.green() + (b.green() - c.green()) * ratio),
        int(c.blue() + (b.blue() - c.blue()) * ratio),
    ).name()


def clear_layout(layout):
    """Xoá sạch widget trong một layout.

    Phải setParent(None) chứ không chỉ deleteLater(): takeAt() chỉ gỡ khỏi
    layout, widget vẫn là con của card và Qt vẫn vẽ nó ở toạ độ cũ cho tới khi
    vòng lặp sự kiện thật sự huỷ — đủ để một dòng cảnh báo cũ nằm đè lên tiêu
    đề thẻ.
    """
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()


def make_plot(title, color, unit=""):
    """PlotWidget pyqtgraph theo theme chung (dùng ở trang Đồ thị)."""
    pw = pg.PlotWidget()
    pw.setBackground(C["panel"])
    pw.setTitle(title, color=C["muted"], size="10pt")
    pw.showGrid(x=True, y=True, alpha=0.12)
    for ax in ("left", "bottom"):
        pw.getAxis(ax).setPen(pg.mkPen(C["border"]))
        pw.getAxis(ax).setTextPen(pg.mkPen(C["dim"]))
    pw.getAxis("left").setLabel(unit, color=C["dim"])
    pw.setMouseEnabled(x=False, y=False)
    pw.setMenuEnabled(False)
    pw.hideButtons()
    curve = pw.plot(pen=pg.mkPen(color, width=2))
    return pw, curve
