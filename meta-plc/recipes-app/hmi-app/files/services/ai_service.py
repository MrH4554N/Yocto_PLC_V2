#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vòng đời của trợ lý AI trong app.

Tách khỏi ihcs_bridge để phân vai rõ ràng:
  • ihcs_bridge — thuần logic: telemetry -> 12 feature -> advisory -> chuỗi
    hiển thị. Không biết gì về Qt, test được độc lập.
  • ai_service  — quản lý trạng thái theo thời gian cho app: nạp artifact một
    lần, nhận mẫu mỗi chu kỳ đọc, chạy suy luận mỗi chu kỳ AI, nuốt lỗi để
    một sự cố AI không bao giờ làm chết vòng thu thập dữ liệu.
"""

from config import ARTIFACT_DIR, SPEED_MAX
from services.ihcs_bridge import IHCSAdvisor, format_advisory


class AIService:
    def __init__(self, artifact_dir=None):
        self._advisor = IHCSAdvisor(artifact_dir or ARTIFACT_DIR)
        self._builder = None
        self._last_obs = None
        self.ready = False
        self.error = None

    # ------------------------------------------------------------------
    @property
    def mode(self):
        return self._advisor.mode

    @property
    def artifact_version(self):
        return self._advisor.artifact_version

    def describe(self):
        """Một dòng mô tả trạng thái AI cho trang Hệ thống."""
        labels = {
            "full": "LSTM cảnh báo + MPC đề xuất setpoint",
            "anomaly_only": "chỉ cảnh báo bất thường (thiếu osqp/scipy)",
            "unavailable": "không nạp được artifact",
        }
        text = labels.get(self.mode, self.mode)
        if self.artifact_version:
            text += f" — artifact {self.artifact_version}"
        return text

    # ------------------------------------------------------------------
    def load(self):
        """Nạp artifact. Không ném lỗi: thất bại thì AI tắt, HMI vẫn chạy."""
        try:
            self.ready = self._advisor.load()
        except Exception as e:
            self.ready = False
            self._advisor.error = f"{type(e).__name__}: {e}"
        self.error = self._advisor.error
        if self.ready:
            self._builder = self._advisor.make_observation_builder()
        return self.ready

    def feed(self, speed_rpm, voltage_v, current_a, setpoint_rpm, ts=None):
        """Nạp một mẫu telemetry. Gọi MỖI chu kỳ đọc, không phải mỗi chu kỳ AI.

        Nhiệt độ ước lượng và tích phân sai số là hệ động học theo thời gian —
        bỏ mẫu sẽ làm lệch giá trị đưa vào model.

        ts: mốc thời gian của mẫu (giây). Để None thì lấy đồng hồ hệ thống —
        đúng cho app chạy thật; truyền tay khi phát lại log hoặc chạy mô phỏng
        nhanh hơn thời gian thực, nếu không dt sẽ sai và mô hình nhiệt lệch.
        """
        if not self.ready or self._builder is None:
            return None
        try:
            self._last_obs = self._builder.update(
                speed_rpm=speed_rpm, voltage_v=voltage_v,
                current_a=current_a, setpoint_rpm=setpoint_rpm, ts=ts)
        except Exception as e:
            self.error = f"lỗi dựng feature: {e}"
            self._last_obs = None
        return self._last_obs

    def advise(self):
        """Chạy một chu kỳ suy luận trên mẫu mới nhất.

        Trả về (advisory, view) — advisory là JSON đầy đủ để log/MQTT, view là
        dict đã format sẵn cho giao diện. Trả None nếu chưa có dữ liệu hoặc lỗi.
        """
        if not self.ready or self._last_obs is None:
            return None
        try:
            advisory = self._advisor.run(self._last_obs)
        except Exception as e:
            self.error = f"lỗi suy luận: {e}"
            return None
        return advisory, format_advisory(advisory, speed_max=SPEED_MAX)
