#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trang CẢNH BÁO — nơi duy nhất tập hợp mọi thứ cần người vận hành để ý.

Gồm hai phần:
  • Ô phê duyệt đề xuất của AI (chỉ bật khi thực sự có đề xuất hợp lệ).
  • Danh sách cảnh báo: đang mở ở trên, đã xử lý ở dưới.

Chế độ advisory-only không đổi: AI không có đường nào tự ghi xuống PLC, nút
ÁP DỤNG ở đây là chữ ký của người vận hành.
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QVBoxLayout, QWidget)

from ui.theme import C
from ui.widgets import AlertRow, StatusPill, clear_layout

# Nhật ký trên màn hình giữ 10 phút; lâu hơn thì tra trong /data/events.
HISTORY_TTL_S = 600.0


class AlertsPage(QWidget):
    apply_requested = pyqtSignal(int)     # tốc độ đề xuất được phê duyệt
    dismiss_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(12)

        root.addWidget(self._build_approval())
        root.addWidget(self._build_list(), stretch=1)
        self._suggest_speed = None

    # ------------------------------------------------------------------
    def _build_approval(self):
        card = QFrame(); card.setObjectName("Card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 13, 16, 13)
        lay.setSpacing(8)

        head = QHBoxLayout()
        t = QLabel("ĐỀ XUẤT CỦA AI"); t.setObjectName("CardTitle")
        self.pill = StatusPill("KHÔNG CÓ ĐỀ XUẤT")
        head.addWidget(t)
        head.addStretch()
        head.addWidget(self.pill)
        lay.addLayout(head)

        self.lbl_text = QLabel("Chưa có đề xuất nào chờ phê duyệt.")
        self.lbl_text.setObjectName("CardHeading")
        self.lbl_text.setWordWrap(True)
        lay.addWidget(self.lbl_text)

        self.lbl_detail = QLabel(" ")
        self.lbl_detail.setObjectName("CardSub")
        self.lbl_detail.setWordWrap(True)
        lay.addWidget(self.lbl_detail)

        row = QHBoxLayout(); row.setSpacing(10)
        self.btn_apply = QPushButton("✔  ÁP DỤNG ĐỀ XUẤT")
        self.btn_apply.setObjectName("Success")
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self._emit_apply)
        self.btn_dismiss = QPushButton("BỎ QUA")
        self.btn_dismiss.setObjectName("Ghost")
        self.btn_dismiss.setEnabled(False)
        self.btn_dismiss.clicked.connect(self.dismiss_requested.emit)
        row.addWidget(self.btn_apply, stretch=2)
        row.addWidget(self.btn_dismiss, stretch=1)
        lay.addLayout(row)

        note = QLabel("Advisory-only: AI chỉ đề xuất, mọi thay đổi setpoint đều "
                      "cần người vận hành phê duyệt trước khi ghi xuống PLC.")
        note.setObjectName("CardSub")
        note.setWordWrap(True)
        lay.addWidget(note)
        return card

    def _build_list(self):
        card = QFrame(); card.setObjectName("Card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(8)

        head = QHBoxLayout()
        t = QLabel("NHẬT KÝ CẢNH BÁO"); t.setObjectName("CardTitle")
        self.lbl_count = QLabel("0 đang mở")
        self.lbl_count.setObjectName("CardSub")
        head.addWidget(t)
        head.addStretch()
        head.addWidget(self.lbl_count)
        lay.addLayout(head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        self.list_box = QVBoxLayout(inner)
        self.list_box.setContentsMargins(0, 0, 6, 0)
        self.list_box.setSpacing(6)
        self.list_box.addStretch()
        self.scroll.setWidget(inner)
        lay.addWidget(self.scroll, stretch=1)
        return card

    # ------------------------------------------------------------------
    def _emit_apply(self):
        if self._suggest_speed is not None:
            self.apply_requested.emit(int(self._suggest_speed))

    def show_suggestion(self, view):
        self._suggest_speed = view["speed"]
        self.pill.set_state("warn", "CHỜ PHÊ DUYỆT")
        self.lbl_text.setText(view["text"])
        self.lbl_detail.setText(view.get("detail", " "))
        self.btn_apply.setEnabled(True)
        self.btn_dismiss.setEnabled(True)

    def clear_suggestion(self, text=None, detail=None):
        self._suggest_speed = None
        self.pill.set_state("off", "KHÔNG CÓ ĐỀ XUẤT")
        self.lbl_text.setText(text or "Chưa có đề xuất nào chờ phê duyệt.")
        self.lbl_detail.setText(detail or " ")
        self.btn_apply.setEnabled(False)
        self.btn_dismiss.setEnabled(False)

    def update_alerts(self, engine):
        clear_layout(self.list_box)

        # Nhật ký giữ lâu hơn thẻ tóm tắt (10 phút) vì đây là chỗ người ta mở
        # ra để TRA lại; bản đầy đủ vẫn nằm trong /data/events/*.jsonl.
        rows = engine.visible(24, expire_after_s=HISTORY_TTL_S)
        active = engine.active
        self.lbl_count.setText(
            f"{len(active)} đang mở · {len(rows) - len(active)} đã xử lý"
            if active else "không có cảnh báo đang mở")

        if not rows:
            empty = QLabel("Chưa có sự kiện nào — mọi thứ đang bình thường.")
            empty.setObjectName("CardSub")
            self.list_box.addWidget(empty)
        for alert in rows:
            self.list_box.addWidget(
                AlertRow(alert, fade=engine.fade_ratio(
                    alert, fade_after_s=HISTORY_TTL_S * 0.6,
                    expire_after_s=HISTORY_TTL_S)))
        self.list_box.addStretch()
