#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Máy trạng thái cảnh báo của HMI.

Giao diện cũ chỉ đẩy chữ ra statusbar khi có sự cố, và không bao giờ thu lại.
Hệ quả là người vận hành thấy hai thứ giống hệt nhau: "AI đang canh và mọi thứ
ổn" với "AI đã chết từ lúc nào". Còn một dòng cảnh báo cũ thì nằm lại trên màn
hình mãi kể cả khi băng tải đã chạy êm trở lại.

Module này quản lý cảnh báo theo NGUỒN (key), mỗi nguồn nhiều nhất một cảnh báo
đang mở:

    raise_alert(key, ...)  mở hoặc cập nhật cảnh báo của nguồn đó
    clear(key, ...)        đóng lại, tự ghi một dòng "đã trở lại bình thường"
    log(...)               sự kiện tức thời (khởi động, ghi setpoint…)

Nhờ vậy trạng thái bình thường là một trạng thái CÓ THẬT, quan sát được: danh
sách cảnh báo đang mở rỗng, và dòng gần nhất nói rõ mọi thứ đã trở lại bình
thường lúc mấy giờ. Module thuần Python, không phụ thuộc Qt.
"""

import time
from collections import deque

SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}
HISTORY_LIMIT = 80


class Alert:
    __slots__ = ("key", "severity", "title", "detail", "ts", "resolved_ts",
                 "action", "payload")

    def __init__(self, key, severity, title, detail="", action=None, payload=None):
        self.key = key
        self.severity = severity
        self.title = title
        self.detail = detail
        self.ts = time.time()
        self.resolved_ts = None
        self.action = action        # nhãn nút hành động, None = chỉ để đọc
        self.payload = payload      # dữ liệu kèm theo (vd: setpoint đề xuất)

    @property
    def resolved(self):
        return self.resolved_ts is not None


class AlertEngine:
    """Giữ danh sách cảnh báo đang mở + lịch sử gần đây."""

    def __init__(self, history_limit=HISTORY_LIMIT):
        self._active = {}                              # key -> Alert
        self._history = deque(maxlen=history_limit)    # Alert đã đóng / sự kiện
        self.revision = 0                              # tăng mỗi lần đổi, UI dựa vào để vẽ lại

    # ------------------------------------------------------------------ ghi
    def raise_alert(self, key, severity, title, detail="", action=None, payload=None):
        """Mở cảnh báo cho một nguồn. Gọi lại cùng key chỉ cập nhật nội dung.

        Không tạo mục mới mỗi chu kỳ AI: bất thường kéo dài 5 phút là MỘT sự
        cố, không phải 60 cảnh báo giống nhau trôi qua màn hình.
        """
        cur = self._active.get(key)
        if cur is not None:
            changed = (cur.severity != severity or cur.title != title
                       or cur.detail != detail)
            cur.severity, cur.title, cur.detail = severity, title, detail
            cur.action, cur.payload = action, payload
            if changed:
                self.revision += 1
            return cur

        alert = Alert(key, severity, title, detail, action, payload)
        self._active[key] = alert
        self.revision += 1
        return alert

    def clear(self, key, title=None, detail=""):
        """Đóng cảnh báo của một nguồn và ghi lại thời điểm phục hồi."""
        alert = self._active.pop(key, None)
        if alert is None:
            return None
        alert.resolved_ts = time.time()
        if title:
            alert.title = title
            alert.detail = detail
        self._history.appendleft(alert)
        self.revision += 1
        return alert

    def log(self, severity, title, detail=""):
        """Sự kiện tức thời — vào thẳng lịch sử, không có gì để đóng lại."""
        event = Alert("event", severity, title, detail)
        event.resolved_ts = event.ts if severity == "info" else None
        self._history.appendleft(event)
        self.revision += 1
        return event

    # ------------------------------------------------------------------ đọc
    @property
    def active(self):
        """Cảnh báo đang mở, nặng trước, mới trước."""
        return sorted(self._active.values(),
                      key=lambda a: (-SEVERITY_ORDER.get(a.severity, 0), -a.ts))

    @property
    def history(self):
        return list(self._history)

    def recent(self, n=6):
        """Cảnh báo đang mở + lịch sử, cắt lấy n dòng mới nhất để hiển thị."""
        return (self.active + self.history)[:n]

    def get(self, key):
        return self._active.get(key)

    def count(self, min_severity="warning"):
        floor = SEVERITY_ORDER.get(min_severity, 1)
        return sum(1 for a in self._active.values()
                   if SEVERITY_ORDER.get(a.severity, 0) >= floor)

    @property
    def worst(self):
        """Mức nặng nhất đang mở: 'critical' | 'warning' | 'info' | None."""
        if not self._active:
            return None
        return max(self._active.values(),
                   key=lambda a: SEVERITY_ORDER.get(a.severity, 0)).severity


# ==========================================================================
# NỐI ADVISORY CỦA AI VÀO MÁY CẢNH BÁO
# ==========================================================================
AI_ANOMALY = "ai_anomaly"        # LSTM thấy bất thường
AI_SUGGEST = "ai_suggest"        # MPC có đề xuất chờ phê duyệt
AI_HEALTH = "ai_health"          # bản thân trợ lý AI không chạy được


def apply_advisory(engine, view):
    """Cập nhật máy cảnh báo từ một chu kỳ advisory.

    view là dict do services.ihcs_bridge.format_advisory() trả về.
    """
    level = view.get("level")
    score = view.get("score")
    state = view.get("state")
    detail = view.get("detail", "")

    # --- bất thường ---
    if level == "critical":
        engine.raise_alert(
            AI_ANOMALY, "critical", "Bất thường vượt ngưỡng nguy hiểm",
            view.get("text", detail))
    elif level == "warning":
        engine.raise_alert(
            AI_ANOMALY, "warning", "Chớm bất thường — theo dõi băng tải",
            detail)
    elif level in ("normal", "warmup"):
        # Chỉ số đã về vùng bình thường: đóng cảnh báo cũ lại thay vì để nó nằm
        # lại trên màn hình, và ghi rõ mốc phục hồi.
        engine.clear(AI_ANOMALY,
                     title="Đã trở lại vận hành bình thường",
                     detail=(f"điểm bất thường {score:.3f} về dưới ngưỡng"
                             if score is not None else "AI không còn báo bất thường"))

    # --- đề xuất chờ phê duyệt ---
    if state == "suggest" and view.get("speed") is not None:
        engine.raise_alert(
            AI_SUGGEST, "info", f"AI đề xuất setpoint {view['speed']} rpm",
            view.get("text", ""), action="ÁP DỤNG", payload=view["speed"])
    else:
        engine.clear(AI_SUGGEST, title="Đề xuất của AI đã hết hiệu lực",
                     detail="chu kỳ mới không còn đề xuất thay đổi setpoint")

    # --- sức khoẻ của chính trợ lý AI ---
    if state == "blocked" and level not in ("critical", "warning"):
        engine.raise_alert(AI_HEALTH, "warning", "AI không đưa được đề xuất",
                           view.get("text", ""))
    else:
        engine.clear(AI_HEALTH, title="AI đã đề xuất lại bình thường")


__all__ = ["Alert", "AlertEngine", "apply_advisory",
           "AI_ANOMALY", "AI_SUGGEST", "AI_HEALTH"]
