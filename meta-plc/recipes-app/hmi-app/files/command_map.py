#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quy đổi giữa tốc độ (rpm) và giá trị thanh ghi lệnh D8116.

Thanh ghi lệnh của rig này điều khiển ĐIỆN ÁP động cơ chứ không phải rpm, và
bão hoà ở rail nguồn 24,8 V khi vượt ~3314. Vì vậy KHÔNG có hệ số tuyến tính
nào đúng: hệ số cũ (raw = 4.087*rpm + 1402) quy 600 rpm ra raw 3854, mà bảng đo
thật cho thấy raw 3854 chạy 971 rpm — sai gần 1,6 lần.

Bảng tra thật nằm trong artifact (``preprocessing/command_calibration.json``,
13 điểm đo từ ai_training_data4.csv). Module này bọc bảng đó lại để cả đường
ghi PLC (core/plc_driver.py) lẫn đường dựng feature cho AI
(services/ihcs_bridge.py) dùng chung một phép quy đổi — hai chỗ lệch nhau thì
AI sẽ học một setpoint khác với setpoint người vận hành thực sự ra lệnh.

Thiếu file hiệu chuẩn thì lùi về hệ số tuyến tính cũ để HMI vẫn điều khiển
được; ``CommandMap.calibrated`` cho biết đang ở chế độ nào.
"""

import json
import os

# Hệ số tuyến tính cũ — chỉ dùng khi không có bảng hiệu chuẩn.
FALLBACK_GAIN = 4.087
FALLBACK_OFFSET = 1402

DEFAULT_RAW_MIN = 2000
DEFAULT_RAW_MAX = 4000

CALIBRATION_REL_PATH = "preprocessing/command_calibration.json"


def load_calibration(artifact_dir):
    """Đọc bảng hiệu chuẩn trong artifact. Trả None nếu không có/không hợp lệ."""
    if not artifact_dir:
        return None
    path = os.path.join(str(artifact_dir), CALIBRATION_REL_PATH)
    try:
        with open(path) as f:
            calib = json.load(f)
    except (OSError, ValueError):
        return None
    return calib if calib.get("anchors") else None


class CommandMap:
    """Bảng tra thanh ghi lệnh <-> tốc độ, hai chiều."""

    def __init__(self, calibration=None, raw_min=DEFAULT_RAW_MIN,
                 raw_max=DEFAULT_RAW_MAX):
        self.raw_min = int(raw_min)
        self.raw_max = int(raw_max)
        self.calibrated = False
        self.rpm_per_volt = None
        self._reg = []
        self._rpm = []
        self._inv_rpm = []
        self._inv_reg = []

        if not calibration or not calibration.get("anchors"):
            return

        anchors = sorted(calibration["anchors"], key=lambda a: a["register"])
        self._reg = [float(a["register"]) for a in anchors]
        self._rpm = [float(a["speed_rpm"]) for a in anchors]
        self.rpm_per_volt = calibration.get("rpm_per_volt")

        # Chiều ngược (rpm -> register) chỉ định nghĩa được ở đoạn CHƯA bão hoà:
        # trên đầu gối bão hoà, thêm register không thêm tốc độ nên tốc độ không
        # còn đơn điệu và phép nội suy ngược sẽ vô nghĩa.
        knee = float(calibration.get("saturation_knee_register", self._reg[-1]))
        for reg, rpm in zip(self._reg, self._rpm):
            if reg > knee:
                break
            if self._inv_rpm and rpm <= self._inv_rpm[-1]:
                continue
            self._inv_rpm.append(rpm)
            self._inv_reg.append(reg)

        self.calibrated = len(self._inv_rpm) >= 2

    # ------------------------------------------------------------------
    @property
    def max_speed_rpm(self):
        """Tốc độ cao nhất còn ra lệnh được (trên mức này thanh ghi bão hoà)."""
        return self._inv_rpm[-1] if self.calibrated else None

    def raw_to_speed(self, raw):
        """Giá trị thanh ghi -> tốc độ vận hành tương ứng (rpm)."""
        if raw is None:
            return None
        raw = float(raw)
        if raw <= 0:
            return 0.0
        if not self._reg:
            return max(0.0, (raw - FALLBACK_OFFSET) / FALLBACK_GAIN)
        return _interp(raw, self._reg, self._rpm)

    def speed_to_raw(self, speed_rpm):
        """Tốc độ mong muốn (rpm) -> giá trị ghi vào D8116."""
        if speed_rpm is None:
            return 0
        speed = float(speed_rpm)
        if speed <= 0:
            return 0                      # 0 = dừng, không phải "chạy chậm nhất"
        if not self.calibrated:
            raw = FALLBACK_GAIN * speed + FALLBACK_OFFSET
        else:
            raw = _interp(speed, self._inv_rpm, self._inv_reg)
        return int(max(self.raw_min, min(self.raw_max, round(raw))))


def _interp(x, xs, ys):
    """Nội suy tuyến tính, kẹp ở hai đầu. xs phải tăng dần."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if x <= xs[i]:
            span = xs[i] - xs[i - 1]
            if span <= 0:
                return ys[i]
            w = (x - xs[i - 1]) / span
            return ys[i - 1] + w * (ys[i] - ys[i - 1])
    return ys[-1]


__all__ = ["CommandMap", "load_calibration", "FALLBACK_GAIN", "FALLBACK_OFFSET"]
