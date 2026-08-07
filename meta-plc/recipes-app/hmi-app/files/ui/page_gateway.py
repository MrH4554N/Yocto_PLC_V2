#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trang GATEWAY — chiếc Pi này nối với ai, đẩy dữ liệu đi đâu, lưu ở đâu.

Bốn thẻ trả lời bốn câu hỏi tách bạch, vì khi số liệu không lên tới CoreIOT thì
mỗi nguyên nhân có một cách sửa khác hẳn:

  MẠNG      — có địa chỉ IP chưa, sóng Wi-Fi thế nào, đường ra Internet là cổng nào
  UPLINK    — tới được broker chưa, đã đẩy bao nhiêu, còn tồn bao nhiêu chờ gửi bù
  THIẾT BỊ  — phía dưới đang đại diện cho những trạm nào
  LƯU TRỮ   — ghi xuống thẻ có chạy không, đã đầy tới đâu
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QVBoxLayout, QWidget)

from ui.theme import C, MONO
from ui.widgets import StatusPill, clear_layout


class GatewayPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(12)

        grid = QGridLayout()
        grid.setSpacing(12)
        grid.addWidget(self._build_network(), 0, 0)
        grid.addWidget(self._build_uplink(), 0, 1)
        grid.addWidget(self._build_devices(), 1, 0)
        grid.addWidget(self._build_storage(), 1, 1)
        root.addLayout(grid, stretch=1)

    # ------------------------------------------------------------------
    @staticmethod
    def _card(title):
        card = QFrame(); card.setObjectName("Card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(6)
        head = QHBoxLayout()
        t = QLabel(title); t.setObjectName("CardTitle")
        pill = StatusPill("—")
        head.addWidget(t); head.addStretch(); head.addWidget(pill)
        lay.addLayout(head)
        return card, lay, pill

    @staticmethod
    def _kv(layout, name):
        row = QHBoxLayout(); row.setSpacing(10)
        lbl = QLabel(name)
        lbl.setStyleSheet(f"font-size: 12px; color: {C['muted']};")
        lbl.setFixedWidth(96)
        val = QLabel("—")
        val.setStyleSheet(f"font-family: {MONO}; font-size: 12px;")
        val.setWordWrap(True)
        row.addWidget(lbl)
        row.addWidget(val, stretch=1)
        layout.addLayout(row)
        return val

    def _build_network(self):
        card, lay, self.pill_net = self._card("MẠNG")
        self.val_iface = self._kv(lay, "Đường ra")
        self.val_ip = self._kv(lay, "Địa chỉ IP")
        self.val_ssid = self._kv(lay, "Wi-Fi")
        self.val_host = self._kv(lay, "Tên máy")
        lay.addStretch()
        return card

    def _build_uplink(self):
        card, lay, self.pill_uplink = self._card("UPLINK COREIOT")
        self.val_broker = self._kv(lay, "Broker")
        self.val_sent = self._kv(lay, "Đã đẩy")
        self.val_queued = self._kv(lay, "Chờ gửi bù")
        self.val_dropped = self._kv(lay, "Bỏ do tràn")
        lay.addStretch()
        return card

    def _build_devices(self):
        card, lay, self.pill_dev = self._card("THIẾT BỊ ĐANG ĐẠI DIỆN")
        self.dev_box = QVBoxLayout()
        self.dev_box.setSpacing(5)
        lay.addLayout(self.dev_box)
        lay.addStretch()
        return card

    def _build_storage(self):
        card, lay, self.pill_store = self._card("LƯU TRỮ DỮ LIỆU")
        self.lbl_storage = QLabel("đang khởi tạo…")
        self.lbl_storage.setWordWrap(True)
        self.lbl_storage.setStyleSheet(f"font-family: {MONO}; font-size: 12px;")
        lay.addWidget(self.lbl_storage)
        lay.addStretch()
        return card

    # ------------------------------------------------------------------
    def update_network(self, info):
        up = info.get("uplink")
        if up:
            self.val_iface.setText(f"{up['name']} ({up['state']})")
            self.val_ip.setText(up.get("ip") or "chưa có IP")
            if up.get("wireless"):
                q = up.get("quality")
                self.val_ssid.setText(
                    f"{up.get('ssid') or 'không rõ SSID'}"
                    + (f"  ·  sóng {q}%" if q is not None else ""))
            else:
                self.val_ssid.setText("dùng dây (không phải Wi-Fi)")
        else:
            self.val_iface.setText("không có tuyến mặc định")
            self.val_ip.setText("—")
            self.val_ssid.setText("—")
        self.val_host.setText(info.get("hostname", "—"))

        if info.get("internet"):
            self.pill_net.set_state("ok", "CÓ ĐƯỜNG RA")
        else:
            self.pill_net.set_state("err", "KHÔNG RA ĐƯỢC")

    def update_uplink(self, broker, port, connected, reachable, sent, queued,
                      dropped):
        self.val_broker.setText(f"{broker}:{port}")
        self.val_sent.setText(f"{sent} gói (phiên này)")
        self.val_queued.setText(f"{queued} gói" if queued else "không có")
        self.val_dropped.setText(f"{dropped} gói" if dropped else "không có")

        # Phân biệt ba tầng hỏng: tới được broker mà chưa đăng nhập được là
        # chuyện token, khác hẳn với không tới được broker (mạng/tường lửa).
        if connected:
            self.pill_uplink.set_state("ok", "ĐANG ĐẨY")
        elif reachable:
            self.pill_uplink.set_state("warn", "TỚI ĐƯỢC, CHƯA ĐĂNG NHẬP")
        else:
            self.pill_uplink.set_state("err", "KHÔNG TỚI ĐƯỢC")

    def update_devices(self, registry, links):
        clear_layout(self.dev_box)
        for station in registry.stations:
            selected = station.id == registry.selected_id
            ok = selected and bool(links.get("plc"))
            row = QHBoxLayout(); row.setSpacing(8)
            dot = QLabel()
            dot.setFixedSize(9, 9)
            dot.setStyleSheet(
                f"background-color: "
                f"{C['ok'] if ok else (C['err'] if selected else C['dim'])};"
                f"border-radius: 4px;")
            name = QLabel(station.name)
            name.setStyleSheet("font-size: 13px; font-weight: 600;")
            state = QLabel("đang giám sát" if selected else "chờ")
            state.setStyleSheet(f"font-size: 11px; color: {C['dim']};")
            row.addWidget(dot)
            row.addWidget(name)
            row.addStretch()
            row.addWidget(state)
            self.dev_box.addLayout(row)

        n_live = 1 if links.get("plc") else 0
        self.pill_dev.set_state("ok" if n_live else "warn",
                                f"{n_live}/{len(registry.stations)} TRẠM")

    def update_storage(self, state, text):
        label = {"ok": "ĐANG GHI", "err": "LỖI GHI", "off": "KHÔNG GHI"}
        self.pill_store.set_state(state, label.get(state, "—"))
        self.lbl_storage.setText(text)
