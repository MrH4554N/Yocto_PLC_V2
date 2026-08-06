#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vòng đời của trợ lý AI trong app.

Tách khỏi ihcs_bridge để phân vai rõ ràng:
  • ihcs_bridge — thuần logic: telemetry -> 10 feature -> advisory -> chuỗi
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
            "anomaly_only": "chỉ cảnh báo bất thường (MPC không chạy được)",
            "unavailable": "không nạp được artifact",
        }
        text = labels.get(self.mode, self.mode)
        if self.artifact_version:
            text += f" — artifact {self.artifact_version}"
        # Chế độ rút gọn/không chạy được thì lý do quan trọng hơn cái nhãn:
        # thiếu thư viện và sai artifact nhìn giống hệt nhau nếu không in ra.
        if self.mode != "full" and self.error:
            text += f"\n{self.error}"
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

    def describe_info(self):
        """Thông tin model cho trang Thiết bị / Cài đặt (dict, an toàn khi lỗi)."""
        advisor = self._advisor
        engine = getattr(advisor, "_engine", None)
        thresholds = getattr(engine, "_anomaly_thresholds", None) or \
            getattr(engine, "_thresholds", None) or {}
        features = getattr(engine, "_feature_list", None) or \
            getattr(engine, "_features", None) or []
        return {
            "mode": self.mode,
            "description": self.describe(),
            "version": self.artifact_version,
            "error": self.error,
            "n_features": len(features),
            "warning_threshold": thresholds.get("warning_threshold"),
            "critical_threshold": thresholds.get("critical_threshold"),
        }

    @property
    def warmup_remaining(self):
        """Số mẫu còn thiếu trước khi chấm được điểm bất thường."""
        engine = getattr(self._advisor, "_engine", None)
        return getattr(engine, "warmup_remaining", 0)

    def reset_window(self):
        """Bỏ cửa sổ đang dở (mất dữ liệu đầu vào) và bắt đầu thu thập lại."""
        if self.ready:
            self._advisor.reset_window()
            if self._builder is not None:
                self._builder.reset()
        self._last_obs = None

    def feed(self, speed_rpm, voltage_v, current_a, cmd_register=None, ts=None):
        """Nạp một mẫu telemetry. Gọi MỖI chu kỳ đọc, không phải mỗi chu kỳ AI.

        Hai lý do phải gọi mỗi chu kỳ: bộ lọc dòng 15 giây là hệ động học theo
        thời gian (bỏ mẫu là lệch giá trị), và model dự báo bước kế tiếp cần
        một cửa sổ 50 mẫu LIÊN TIẾP mới chấm điểm được.

        cmd_register: giá trị thô của thanh ghi lệnh D8116. Thiếu nó thì
        ObservationBuilder chạy chế độ suy giảm (suy điểm làm việc từ điện áp)
        — vẫn phát hiện lỗi cơ khí, nhưng không còn phát hiện lỗi bám lệnh.

        ts: mốc thời gian của mẫu (giây). Để None thì lấy đồng hồ hệ thống —
        đúng cho app chạy thật; truyền tay khi phát lại log hoặc chạy mô phỏng
        nhanh hơn thời gian thực, nếu không dt sẽ sai và bộ lọc dòng lệch.
        """
        if not self.ready or self._builder is None:
            return None
        try:
            self._last_obs = self._builder.update(
                speed_rpm=speed_rpm, voltage_v=voltage_v,
                current_a=current_a, cmd_register=cmd_register, ts=ts)
            self._advisor.observe(self._last_obs, ts=ts)
        except Exception as e:
            self.error = f"lỗi dựng feature: {e}"
            self._last_obs = None
        return self._last_obs

    def advise(self, ts=None):
        """Chạy một chu kỳ suy luận trên mẫu mới nhất.

        Trả về (advisory, view) — advisory là JSON đầy đủ để log/MQTT, view là
        dict đã format sẵn cho giao diện. Trả None nếu chưa có dữ liệu hoặc lỗi.

        ts: truyền cùng mốc thời gian đã dùng cho feed() khi phát lại log; để
        None thì cả hai cùng lấy đồng hồ hệ thống.
        """
        if not self.ready or self._last_obs is None:
            return None
        try:
            advisory = self._advisor.run(self._last_obs, ts=ts)
        except Exception as e:
            self.error = f"lỗi suy luận: {e}"
            return None
        return advisory, format_advisory(advisory, speed_max=SPEED_MAX)
