#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trang TRẠM — chọn PLC nào để giám sát.

Bấm vào một trạm là chuyển toàn bộ các tab Giám sát / Đồ thị / Điều khiển sang
trạm đó. Trạm đang chọn có viền sáng, các trạm còn lại nằm im (HMI chỉ mở một
cổng nối tiếp tại một thời điểm — đọc song song nhiều cổng sẽ phá nhịp 0,5 giây
mà AI đang dựa vào).

Danh sách đọc từ /data/devices.json; thêm/bớt trạm bằng cách sửa file đó.
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QVBoxLayout, QWidget)

from ui.theme import C, MONO
from ui.widgets import StatusPill, clear_layout


class StationRow(QFrame):
    """Một dòng trạm: tên + thông số cổng + trạng thái + nút chọn."""

    chosen = pyqtSignal(str)

    def __init__(self, station, selected, link_ok, live_text, parent=None):
        super().__init__(parent)
        self.setObjectName("Sunken")
        if selected:
            self.setStyleSheet(
                f"QFrame#Sunken {{ border: 1px solid {C['volt']}; }}")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 11, 14, 11)
        lay.setSpacing(12)

        dot = QLabel("●")
        dot.setFixedWidth(16)
        color = C["ok"] if (selected and link_ok) else (
            C["err"] if selected else C["dim"])
        dot.setStyleSheet(f"color: {color}; font-size: 14px;")

        box = QVBoxLayout(); box.setSpacing(2)
        name = QLabel(f"{station.name}")
        name.setStyleSheet("font-size: 15px; font-weight: 700;")
        sub = QLabel(station.summary)
        sub.setStyleSheet(f"font-family: {MONO}; font-size: 11px; color: {C['dim']};")
        box.addWidget(name)
        box.addWidget(sub)

        self.live = QLabel(live_text)
        live = self.live
        live.setStyleSheet(
            f"font-family: {MONO}; font-size: 13px; color: {C['muted']};")
        live.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        pill = StatusPill("ĐANG GIÁM SÁT" if selected else "CHỜ")
        pill.set_state("ok" if selected and link_ok else
                       ("err" if selected else "off"),
                       "ĐANG GIÁM SÁT" if selected else "CHỜ")

        btn = QPushButton("ĐANG XEM" if selected else "MỞ →")
        btn.setObjectName("Chip")
        btn.setMinimumHeight(34)
        btn.setMinimumWidth(92)
        btn.setEnabled(not selected)
        btn.clicked.connect(lambda: self.chosen.emit(station.id))

        lay.addWidget(dot)
        lay.addLayout(box, stretch=1)
        lay.addWidget(live)
        lay.addWidget(pill)
        lay.addWidget(btn)


class StationsPage(QWidget):
    station_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(12)

        card = QFrame(); card.setObjectName("Card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 13, 16, 13)
        lay.setSpacing(8)

        head = QHBoxLayout()
        t = QLabel("TRẠM PLC"); t.setObjectName("CardTitle")
        self.lbl_count = QLabel("—")
        self.lbl_count.setObjectName("CardSub")
        head.addWidget(t); head.addStretch(); head.addWidget(self.lbl_count)
        lay.addLayout(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        self.list_box = QVBoxLayout(inner)
        self.list_box.setContentsMargins(0, 0, 6, 0)
        self.list_box.setSpacing(8)
        self.list_box.addStretch()
        scroll.setWidget(inner)
        lay.addWidget(scroll, stretch=1)
        root.addWidget(card, stretch=1)

        note = QLabel("Thêm hoặc sửa trạm: /data/devices.json — "
                      "HMI chỉ giám sát trạm đang chọn.")
        note.setObjectName("CardSub")
        root.addWidget(note)

        self._telemetry = {}
        self._rows = {}

    # ------------------------------------------------------------------
    def update_registry(self, registry, links):
        clear_layout(self.list_box)
        self._rows = {}
        stations = registry.stations
        self.lbl_count.setText(
            f"{len(stations)} trạm · đang giám sát {registry.selected_id}")
        for station in stations:
            selected = station.id == registry.selected_id
            live = self._telemetry.get(station.id, "—")
            row = StationRow(station, selected, bool(links.get("plc")), live)
            row.chosen.connect(self.station_selected.emit)
            self._rows[station.id] = row
            self.list_box.addWidget(row)
        self.list_box.addStretch()

        if registry.error:
            err = QLabel(f"Lỗi đọc devices.json: {registry.error}")
            err.setStyleSheet(f"color: {C['err']}; font-size: 12px;")
            err.setWordWrap(True)
            self.list_box.addWidget(err)

    def update_telemetry(self, station_id, d):
        """Số liệu sống của trạm đang giám sát, hiện ngay trên dòng của nó.

        Ghi thẳng vào nhãn thay vì dựng lại cả danh sách: telemetry về 2 lần
        mỗi giây, dựng lại vài chục widget với nhịp đó là phí CPU của Pi.
        """
        text = (f"{d['speed']:.0f} rpm   {d['voltage']:.1f} V   "
                f"{d['current']:.3f} A")
        self._telemetry[station_id] = text
        row = self._rows.get(station_id)
        if row is not None:
            row.live.setText(text)
