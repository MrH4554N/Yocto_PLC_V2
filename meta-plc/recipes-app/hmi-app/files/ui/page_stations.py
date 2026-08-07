#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Màn hình CHỌN HỆ THỐNG — cửa vào của app.

Đây là trang mở lên đầu tiên và nó cố tình KHÔNG có thanh tab: chừng nào chưa
chọn hệ thống thì Giám sát / Đồ thị / Điều khiển chưa có nghĩa gì, hiện chúng
ra chỉ khiến người vận hành bấm vào và nhìn một trang trống.

Mỗi hệ thống là một thẻ lớn bấm được cả thẻ — màn hình này là màn cảm ứng đặt
trong xưởng, người bấm có thể đang đeo găng, nên vùng bấm phải to chứ không
phải một cái nút con ở mép phải.
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QScrollArea, QVBoxLayout, QWidget)

from ui.theme import C, MONO
from ui.widgets import clear_layout

CARDS_PER_ROW = 3


class StationCard(QFrame):
    """Thẻ một hệ thống: số thứ tự lớn, tên, thông số cổng, trạng thái."""

    chosen = pyqtSignal(str)

    def __init__(self, index, station, selected, link_ok, live_text, parent=None):
        super().__init__(parent)
        self.station_id = station.id
        self.setObjectName("Card")
        self.setMinimumHeight(196)
        self.setCursor(Qt.PointingHandCursor)
        if selected:
            self.setStyleSheet(
                f"QFrame#Card {{ border: 2px solid {C['volt']}; }}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(4)

        top = QHBoxLayout()
        num = QLabel(str(index))
        num.setStyleSheet(
            f"font-family: {MONO}; font-size: 40px; font-weight: 800; "
            f"color: {C['volt'] if selected else C['dim']};")
        state = QLabel("ĐANG GIÁM SÁT" if selected else "CHỜ")
        state.setStyleSheet(
            f"font-size: 11px; font-weight: 800; letter-spacing: 1px;"
            f"color: {(C['ok'] if link_ok else C['err']) if selected else C['dim']};")
        state.setAlignment(Qt.AlignTop | Qt.AlignRight)
        top.addWidget(num)
        top.addStretch()
        top.addWidget(state)
        lay.addLayout(top)

        name = QLabel(station.name)
        name.setStyleSheet("font-size: 18px; font-weight: 700;")
        name.setWordWrap(True)
        lay.addWidget(name)

        sub = QLabel(station.summary.replace(" · ", "\n"))
        sub.setStyleSheet(f"font-family: {MONO}; font-size: 11px; color: {C['dim']};")
        lay.addWidget(sub)
        lay.addStretch()

        self.live = QLabel(live_text)
        self.live.setStyleSheet(
            f"font-family: {MONO}; font-size: 13px; "
            f"color: {C['muted'] if selected else C['dim']};")
        lay.addWidget(self.live)

    def mouseReleaseEvent(self, event):
        # Bấm chỗ nào trên thẻ cũng vào được, không phải nhắm đúng cái nút.
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.chosen.emit(self.station_id)
        super().mouseReleaseEvent(event)


class StationsPage(QWidget):
    station_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 14)
        root.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("CHỌN HỆ THỐNG")
        title.setStyleSheet("font-size: 20px; font-weight: 800; letter-spacing: 2px;")
        self.lbl_count = QLabel("—")
        self.lbl_count.setObjectName("CardSub")
        head.addWidget(title)
        head.addStretch()
        head.addWidget(self.lbl_count)
        root.addLayout(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        self.grid = QGridLayout(inner)
        self.grid.setContentsMargins(0, 0, 6, 0)
        self.grid.setSpacing(14)
        scroll.setWidget(inner)
        root.addWidget(scroll, stretch=1)

        self.note = QLabel("Chạm vào một hệ thống để mở giám sát. "
                           "Thêm hoặc sửa: /data/devices.json")
        self.note.setObjectName("CardSub")
        root.addWidget(self.note)

        self._telemetry = {}
        self._cards = {}

    # ------------------------------------------------------------------
    def update_registry(self, registry, links):
        clear_layout(self.grid)
        self._cards = {}
        stations = registry.stations
        self.lbl_count.setText(f"{len(stations)} hệ thống")

        for i, station in enumerate(stations):
            selected = station.id == registry.selected_id
            card = StationCard(i + 1, station, selected, bool(links.get("plc")),
                               self._telemetry.get(station.id, "chưa có số liệu"))
            card.chosen.connect(self.station_selected.emit)
            self._cards[station.id] = card
            self.grid.addWidget(card, i // CARDS_PER_ROW, i % CARDS_PER_ROW)

        # Cột trống ở hàng cuối vẫn phải giữ bề rộng, nếu không thẻ lẻ sẽ bị
        # kéo giãn ra chiếm cả hàng và to gấp ba thẻ bên cạnh.
        for c in range(CARDS_PER_ROW):
            self.grid.setColumnStretch(c, 1)
        self.grid.setRowStretch(self.grid.rowCount(), 1)

        if registry.error:
            err = QLabel(f"Lỗi đọc devices.json: {registry.error}")
            err.setStyleSheet(f"color: {C['err']}; font-size: 12px;")
            err.setWordWrap(True)
            self.grid.addWidget(err, self.grid.rowCount(), 0, 1, CARDS_PER_ROW)

    def update_telemetry(self, station_id, d):
        """Ghi thẳng vào nhãn — telemetry về 2 lần/giây, dựng lại thẻ là phí CPU."""
        text = (f"{d['speed']:.0f} rpm   {d['voltage']:.1f} V   "
                f"{d['current']:.3f} A")
        self._telemetry[station_id] = text
        card = self._cards.get(station_id)
        if card is not None:
            card.live.setText(text)
