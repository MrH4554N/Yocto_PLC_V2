#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cầu nối giữa telemetry của HMI và runtime advisory IHCS.

HMI đo được 4 kênh: tốc độ (D120), thanh ghi lệnh (D8116) qua Computer Link,
điện áp và dòng điện (INA219/INA226 qua I2C). Artifact IHCS cần đủ 10 feature
theo ``preprocessing/feature_list.json``. Module này lấp khoảng trống đó:

  • ObservationBuilder — dựng 10 feature từ 4 phép đo, dùng đúng công thức của
    Phase_1 ``preprocessing/derive_signals.py`` để dữ liệu suy luận trùng phân
    phối với dữ liệu huấn luyện.
  • IHCSAdvisor       — nạp artifact, chạy advisory, tự hạ cấp xuống chế độ
    chỉ-phát-hiện-bất-thường nếu image thiếu osqp/scipy (phần MPC).
  • format_advisory   — đổi advisory JSON thành chuỗi hiển thị cho HMI.

Chế độ advisory-only được giữ nguyên: module này KHÔNG ghi PLC.

MỌI ĐẶC TRƯNG ĐỀU NHÂN QUẢ: chỉ tính từ mẫu tại thời điểm <= t (cửa sổ
TRAILING). Lúc train dùng đúng định nghĩa này, và ở runtime cũng không thể
nhìn thấy mẫu tương lai.
"""

import json
import math
import os
import sys
import time
from collections import deque
from pathlib import Path

import numpy as np

try:
    from command_map import CommandMap
except ImportError:   # chạy trực tiếp file này: thư mục gốc app chưa có trong sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from command_map import CommandMap

DEFAULT_ARTIFACT_DIR = os.environ.get(
    "IHCS_ARTIFACT_DIR", "/usr/share/hmi-app/artifact")

# Cửa sổ trailing của bộ lọc dòng — khớp current_filter_window_s lúc train.
CURRENT_FILTER_WINDOW_S = 15.0
# Dưới mức này coi như động cơ không được cấp điện (khớp derive_signals.py).
MIN_VOLTAGE_FOR_RATIO_V = 1.0
# Nhịp lấy mẫu lúc train, dùng làm khoảng tính gia tốc.
DEFAULT_SAMPLE_PERIOD_S = 1.0

# Các kênh gửi kèm advisory cho người vận hành / MQTT.
CURRENT_STATE_KEYS = [
    "setpoint_rpm", "speed_rpm", "tracking_error_rpm",
    "current_a", "current_lp15_a", "voltage_v", "power_w",
]


# ==========================================================================
# DỰNG OBSERVATION
# ==========================================================================
class ObservationBuilder:
    """Suy ra 10 feature của artifact từ telemetry thô của HMI.

    Gọi update() mỗi chu kỳ đọc phần cứng (không phải mỗi chu kỳ AI) — bộ lọc
    dòng 15 giây và gia tốc là hệ động học theo thời gian, bỏ mẫu sẽ làm lệch
    giá trị.

    Cửa sổ tính theo THỜI GIAN chứ không theo số mẫu: HMI đọc 2 Hz còn model
    học ở 1 Hz, nếu đếm mẫu thì "15 mẫu" ở runtime chỉ trải 7,5 giây và bộ lọc
    sẽ có ý nghĩa khác hẳn thứ nó được dạy.
    """

    def __init__(self, system_parameters: dict, command_calibration: dict = None):
        motor = system_parameters.get("motor", {})
        sampling = system_parameters.get("sampling", {})

        period_ms = sampling.get("resample_period_ms")
        self.sample_period_s = (float(period_ms) / 1000.0 if period_ms
                                else DEFAULT_SAMPLE_PERIOD_S)
        self.current_window_s = float(
            system_parameters.get("current_filter_window_s",
                                  CURRENT_FILTER_WINDOW_S))

        # Thanh ghi lệnh điều khiển ĐIỆN ÁP và bão hoà ở rail nguồn, nên
        # setpoint_rpm phải tra bảng đo được. Không có bảng (hoặc không đọc
        # được thanh ghi) thì suy từ điện áp đang đặt vào — xem degraded bên
        # dưới.
        self.command_map = CommandMap(command_calibration)
        self.rpm_per_volt = float(
            motor.get("rpm_per_volt")
            or (command_calibration or {}).get("rpm_per_volt")
            or 0.0)
        self.degraded_no_register = False

        # --- trạng thái tích lũy ---
        self.current_hist = deque()      # (ts, current_a) trong 15 giây gần nhất
        self.speed_hist = deque()        # (ts, speed_rpm) đủ để tính gia tốc 1 s
        self.n_samples = 0

    def reset(self):
        self.current_hist.clear()
        self.speed_hist.clear()
        self.degraded_no_register = False
        self.n_samples = 0

    def setpoint_from(self, voltage_v, cmd_register=None):
        """Điểm làm việc được lệnh, quy ra rpm.

        Có thanh ghi thì tra bảng hiệu chuẩn (13 điểm đo thật). Không có thì
        chạy CHẾ ĐỘ SUY GIẢM: suy từ điện áp đang đặt vào. Vẫn phát hiện được
        lỗi cơ khí, nhưng tracking_error_rpm không còn phản ánh lỗi bám lệnh.
        """
        if cmd_register is not None:
            return self.command_map.raw_to_speed(cmd_register)
        self.degraded_no_register = True
        return float(voltage_v) * self.rpm_per_volt

    def update(self, speed_rpm, voltage_v, current_a, cmd_register=None,
               setpoint_rpm=None, ts=None):
        """Cập nhật một mẫu telemetry, trả về observation đầy đủ 10 feature.

        setpoint_rpm chỉ dùng khi người gọi đã tự quy đổi (phát lại log đã có
        sẵn cột này); đường chạy thật truyền cmd_register.
        """
        ts = time.monotonic() if ts is None else float(ts)

        speed = float(speed_rpm)
        voltage = float(voltage_v)
        current = float(current_a)
        setpoint = (float(setpoint_rpm) if setpoint_rpm is not None
                    else self.setpoint_from(voltage, cmd_register))

        # --- bộ lọc dòng: trung bình + độ lệch chuẩn trên cửa sổ trailing ---
        # Đẩy mẫu vào TRƯỚC khi tính: cửa sổ trailing bao gồm cả mẫu hiện tại,
        # đúng thứ một bộ lọc nhân quả nhìn thấy ở runtime.
        # Bỏ mẫu đã đủ 15 giây tuổi (so sánh >=) để ở nhịp 1 Hz cửa sổ giữ đúng
        # 15 mẫu như deque(maxlen=15) lúc train.
        self.current_hist.append((ts, current))
        while self.current_hist and ts - self.current_hist[0][0] >= self.current_window_s:
            self.current_hist.popleft()
        window = [c for _, c in self.current_hist]
        current_lp = sum(window) / len(window)
        if len(window) >= 2:
            var = sum((c - current_lp) ** 2 for c in window) / (len(window) - 1)
            current_ripple = math.sqrt(var)
        else:
            current_ripple = 0.0

        # --- gia tốc trên đúng nhịp lấy mẫu lúc train ---
        # Lấy hiệu tốc độ qua 1 giây chứ không qua một chu kỳ đọc: chia hiệu
        # của 0,5 giây cho 0,5 vẫn ra rpm/s nhưng nhiễu lượng tử gấp đôi, và
        # model đã học phân phối của nhịp 1 giây.
        self.speed_hist.append((ts, speed))
        while (len(self.speed_hist) >= 2
               and ts - self.speed_hist[1][0] >= self.sample_period_s):
            self.speed_hist.popleft()
        t0, speed0 = self.speed_hist[0]
        accel = (speed - speed0) / (ts - t0) if ts > t0 else 0.0

        # --- tỉ số rpm/V: chỉ báo sức khoẻ cơ khí ---
        # Sụt tỉ số này ở cùng một mức lệnh chính là dấu hiệu kẹt cơ khí, quá
        # tải dây đai hay mòn chổi than.
        if voltage > MIN_VOLTAGE_FOR_RATIO_V:
            speed_per_volt = speed / voltage
        else:
            speed_per_volt = 0.0     # mất điện áp là trạng thái thật, không phải thiếu dữ liệu

        self.n_samples += 1

        return {
            "setpoint_rpm": setpoint,
            "speed_rpm": speed,
            "voltage_v": voltage,
            "current_a": current,
            "current_lp15_a": current_lp,
            "tracking_error_rpm": setpoint - speed,
            "accel_rpm_s": accel,
            "power_w": voltage * current,
            "speed_per_volt_rpm_v": speed_per_volt,
            "current_ripple_a": current_ripple,
        }


# ==========================================================================
# ADVISOR
# ==========================================================================
class IHCSAdvisor:
    """Nạp artifact IHCS và chạy một chu kỳ advisory.

    mode:
      "full"         — LSTM anomaly + MPC đề xuất setpoint (đủ osqp + scipy)
      "anomaly_only" — thiếu osqp/scipy: chỉ cảnh báo bất thường, không đề xuất
      "unavailable"  — không nạp được artifact (HMI chạy tiếp, tắt tính năng AI)
    """

    def __init__(self, artifact_dir=None):
        self.artifact_dir = str(artifact_dir or DEFAULT_ARTIFACT_DIR)
        self.mode = "unavailable"
        self.error = None
        self.artifact_version = None
        self.system_parameters = {}
        self.command_calibration = {}
        self._engine = None
        self._loader = None

    @property
    def available(self):
        return self.mode in ("full", "anomaly_only")

    def load(self):
        """Nạp + kiểm tra checksum artifact. Trả về True nếu dùng được."""
        try:
            from ihcs.runtime.artifact_loader import ArtifactLoader
            loader = ArtifactLoader(self.artifact_dir)
            manifest = loader.load_and_verify()
            self._loader = loader
            self.artifact_version = manifest.get("artifact_version")
            try:
                self.system_parameters = loader.load_json(
                    "preprocessing/system_parameters.json")
            except FileNotFoundError:
                self.system_parameters = {}
            try:
                self.command_calibration = loader.load_json(
                    "preprocessing/command_calibration.json")
            except FileNotFoundError:
                self.command_calibration = {}
        except Exception as e:
            self.mode = "unavailable"
            self.error = f"{type(e).__name__}: {e}"
            return False

        # Ưu tiên engine đầy đủ; thiếu osqp/scipy thì hạ cấp chứ không tắt hẳn.
        try:
            from ihcs.runtime.inference_engine import InferenceEngine
            engine = InferenceEngine(loader)
            engine.load()
            self._engine = engine
            self.mode = "full"
            self.error = None
            return True
        except ImportError as e:
            self.error = f"thiếu thư viện MPC ({e}) — chạy chế độ chỉ phát hiện bất thường"
        except Exception as e:
            self.error = f"MPC không nạp được ({type(e).__name__}: {e}) — chạy chế độ chỉ phát hiện bất thường"

        try:
            # Truyền nguyên văn lý do MPC hỏng xuống engine rút gọn: nếu không,
            # advisory chỉ nói "mpc_unavailable" và giao diện buộc phải đoán —
            # thiếu thư viện, sai artifact hay lỗi cấu hình đều hiện như nhau.
            self._engine = _AnomalyOnlyEngine(loader, reason=self.error)
            self._engine.load()
            self.mode = "anomaly_only"
            return True
        except Exception as e:
            self._engine = None
            self.mode = "unavailable"
            self.error = f"{type(e).__name__}: {e}"
            return False

    def observe(self, observation, ts=None):
        """Nạp một mẫu vào cửa sổ của model dự báo bước kế tiếp.

        Gọi MỖI chu kỳ đọc phần cứng. Model nhận 49 bước liên tiếp rồi đoán
        bước thứ 50, nên nó cần lịch sử thật — không có cửa sổ thì không có
        điểm bất thường. Engine tự bỏ mẫu đến dày hơn nhịp lấy mẫu lúc train.
        """
        if self._engine is None:
            return False
        return self._engine.observe(observation, ts=ts)

    def reset_window(self):
        """Xoá cửa sổ đang dở — gọi khi luồng dữ liệu đầu vào bị đứt."""
        if self._engine is not None:
            self._engine.reset_window()

    def run(self, observation, ts=None):
        """Chạy một chu kỳ advisory. Trả về advisory JSON (dict)."""
        if self._engine is None:
            raise RuntimeError("advisor chưa nạp được artifact")
        return self._engine.run_advisory(observation, ts=ts)

    def make_observation_builder(self):
        return ObservationBuilder(self.system_parameters, self.command_calibration)


class _AnomalyOnlyEngine:
    """Engine rút gọn khi image chưa có osqp/scipy.

    Dùng lại đúng scaler + ONNX của artifact để tính điểm bất thường, nhưng
    không giải QP nên không đề xuất setpoint: advisory luôn bị chặn với
    block_reason="mpc_unavailable". Giữ nguyên định dạng advisory để HMI và
    format_advisory() không cần biết đang chạy chế độ nào.
    """

    def __init__(self, loader, reason=None):
        self._loader = loader
        self._manifest = loader.manifest
        self._reason = reason
        self._features = []
        self._mean = None
        self._scale = None
        self._thresholds = {}
        self._window_size = 49
        self._sample_period_s = DEFAULT_SAMPLE_PERIOD_S
        self._window = deque()
        self._last_admit_ts = None
        self._session = None

    def load(self):
        features = self._loader.load_json("preprocessing/feature_list.json")
        if isinstance(features, dict):
            features = features.get("features", [])
        self._features = [str(f) for f in features]

        scaler = self._loader.load_json("preprocessing/scaler.json")
        n = len(self._features)
        mean = scaler.get("mean_", scaler.get("mean", [0.0] * n))
        scale = scaler.get("scale_", scaler.get("scale", [1.0] * n))
        self._mean = np.asarray(mean, dtype=np.float32)
        scale_arr = np.asarray(scale, dtype=np.float32)
        self._scale = np.where(scale_arr == 0, 1.0, scale_arr)

        try:
            self._thresholds = self._loader.load_json("lstm_anomaly/thresholds.json")
        except FileNotFoundError:
            self._thresholds = {}
        try:
            self._window_size = int(self._loader.load_json(
                "lstm_anomaly/window_config.json").get("window_size", 49))
        except FileNotFoundError:
            pass
        try:
            period_ms = self._loader.load_json(
                "preprocessing/system_parameters.json").get(
                    "sampling", {}).get("resample_period_ms")
            if period_ms:
                self._sample_period_s = float(period_ms) / 1000.0
        except FileNotFoundError:
            pass

        # window_size là số bước ĐẦU VÀO; thêm một ô nữa giữ mẫu thật để chấm
        # điểm dự báo.
        self._window = deque(maxlen=self._window_size + 1)

        import onnxruntime as ort
        self._session = ort.InferenceSession(
            self._loader.model_path("lstm_anomaly/model.onnx"))

    @property
    def warmup_remaining(self):
        return max(0, self._window_size + 1 - len(self._window))

    def reset_window(self):
        self._window.clear()
        self._last_admit_ts = None

    def observe(self, observation, ts=None):
        ts = time.monotonic() if ts is None else float(ts)
        if (self._last_admit_ts is not None
                and (ts - self._last_admit_ts) < self._sample_period_s * 0.98):
            return False

        raw = np.array([float(observation.get(f, 0.0)) for f in self._features],
                       dtype=np.float32)
        if not np.all(np.isfinite(raw)):
            return False

        self._last_admit_ts = ts
        self._window.append((raw - self._mean) / self._scale)
        return True

    def run_advisory(self, observation, ts=None):
        from datetime import datetime, timezone

        self.observe(observation, ts=ts)

        anomaly_score = None
        if len(self._window) > self._window_size:
            window = np.stack(list(self._window))
            inputs = window[:-1][None, :, :].astype(np.float32)
            target = window[-1]
            try:
                out = self._session.run(
                    None, {self._session.get_inputs()[0].name: inputs})
                pred = np.asarray(out[0], dtype=np.float32).reshape(-1)
                anomaly_score = float(np.mean((pred - target) ** 2))
            except Exception:
                anomaly_score = None

        warning = self._thresholds.get("warning_threshold")
        critical = self._thresholds.get("critical_threshold")
        if anomaly_score is not None and critical is not None and anomaly_score >= critical:
            block_reason = (f"anomaly_score {anomaly_score:.4f} >= critical "
                            f"threshold {critical:.4f}")
        else:
            block_reason = "mpc_unavailable"

        return {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "mode": "advisory_only",
            "system_id": "ihcs_servo_conveyor",
            "current_state": {k: observation.get(k) for k in CURRENT_STATE_KEYS},
            "recommendation": {
                "type": "pid_setpoint_recommendation",
                "recommended_delta_setpoint_rpm": None,
                "recommended_setpoint_rpm": None,
                "confidence": 0.0,
                "block_reason": block_reason,
            },
            "model_evidence": {
                "mpc_controller_version": self._manifest.get("artifact_version", "unknown"),
                "mpc_solver_status": "unavailable",
                "mpc_unavailable_reason": self._reason,
                "lstm_anomaly_score": (round(anomaly_score, 6)
                                       if anomaly_score is not None else None),
                "anomaly_threshold": warning,
                "anomaly_critical_threshold": critical,
                "anomaly_warmup_remaining": self.warmup_remaining,
            },
            "safety": {
                "safety_envelope": "blocked",
                "human_approval_required": True,
                "autonomous_action": False,
                "plc_write_performed": False,
                "plc_write_allowed": False,
            },
            "rag_context": {"status": "not_configured", "sources": []},
            "operator_action_required": True,
        }


# ==========================================================================
# HIỂN THỊ
# ==========================================================================
def anomaly_level(advisory):
    """'normal' | 'warning' | 'critical' | 'warmup' | 'unknown' theo ngưỡng artifact."""
    ev = advisory.get("model_evidence", {})
    score = ev.get("lstm_anomaly_score")
    warning = ev.get("anomaly_threshold")
    if score is None:
        return "warmup" if ev.get("anomaly_warmup_remaining") else "unknown"
    envelope = advisory.get("safety", {}).get("safety_envelope")
    reason = (advisory.get("recommendation", {}).get("block_reason") or "")
    if envelope == "blocked" and reason.startswith("anomaly_score"):
        return "critical"
    if warning is not None and score >= warning:
        return "warning"
    return "normal"


def format_advisory(advisory, speed_max=980, min_delta_rpm=1.0):
    """Đổi advisory JSON thành thứ HMI hiển thị được.

    Trả về dict:
      state  — "suggest" (cần phê duyệt) | "normal" | "warmup" | "blocked"
      text   — nội dung chính
      detail — dòng phụ (điểm bất thường, độ tin cậy, trạng thái solver)
      speed  — setpoint đề xuất đã làm tròn/kẹp biên, None nếu không có
      level  — mức bất thường: normal/warning/critical/warmup/unknown
      score  — điểm bất thường thô, None khi chưa chấm được
    """
    rec = advisory.get("recommendation", {})
    ev = advisory.get("model_evidence", {})
    level = anomaly_level(advisory)

    score = ev.get("lstm_anomaly_score")
    warn = ev.get("anomaly_threshold")
    warmup = ev.get("anomaly_warmup_remaining") or 0
    if score is not None and warn is not None:
        score_txt = "bất thường %.4f / ngưỡng %.4f" % (score, warn)
    elif level == "warmup":
        # Model dự báo bước kế tiếp cần 50 mẫu liên tiếp @1 Hz mới chấm điểm
        # được. Nói rõ còn bao nhiêu thay vì báo "không có dữ liệu".
        score_txt = "đang thu thập cửa sổ dữ liệu (còn %d mẫu)" % warmup
    else:
        score_txt = "bất thường: không có dữ liệu"

    block_reason = rec.get("block_reason")
    if block_reason:
        if block_reason == "mpc_unavailable":
            # Nói đúng lý do đo được, không đoán: engine rút gọn chạy cả khi
            # thiếu thư viện lẫn khi artifact/cấu hình sai, và hai thứ đó cần
            # hai cách xử lý hoàn toàn khác nhau.
            reason = ev.get("mpc_unavailable_reason") or "chưa rõ nguyên nhân"
            text = ("Chưa chạy được bộ tối ưu MPC — AI chỉ giám sát bất "
                    f"thường, không đề xuất setpoint.\nLý do: {reason}")
        elif block_reason.startswith("anomaly_score"):
            text = ("CẢNH BÁO: dữ liệu vận hành lệch xa vùng bình thường.\n"
                    "AI chặn mọi đề xuất — kiểm tra băng tải, tải trọng và nguồn điện.")
        else:
            text = ("Không tạo được đề xuất an toàn ở chu kỳ này.\n"
                    f"Lý do: {block_reason}")
        return {"state": "blocked", "text": text,
                "detail": f"{score_txt}   •   {block_reason}",
                "speed": None, "level": level, "score": score}

    setpoint = rec.get("recommended_setpoint_rpm")
    delta = rec.get("recommended_delta_setpoint_rpm") or 0.0
    if setpoint is None:
        return {"state": "blocked",
                "text": "Không có đề xuất ở chu kỳ này.",
                "detail": score_txt, "speed": None, "level": level, "score": score}

    speed = int(round(max(0.0, min(float(speed_max), float(setpoint)))))
    confidence = rec.get("confidence")
    conf_txt = f"độ tin cậy {confidence * 100:.0f}%" if confidence is not None else ""
    solver = ev.get("mpc_solver_status", "?")
    detail = f"{score_txt}   •   {conf_txt}   •   MPC: {solver}"

    # Chưa đủ cửa sổ thì LSTM chưa giám sát được gì. MPC vẫn giải ra số, nhưng
    # mời người vận hành phê duyệt một đề xuất KHÔNG có lớp giám sát bất thường
    # đứng sau là bán một sự bảo đảm không tồn tại — nói thẳng đang khởi động.
    if level == "warmup":
        return {"state": "warmup",
                "text": (f"AI đang thu thập dữ liệu vận hành (còn {warmup} mẫu, "
                         f"~{warmup} giây).\nChưa chấm được điểm bất thường nên "
                         f"chưa đưa đề xuất nào để phê duyệt."),
                "detail": detail, "speed": None, "level": level, "score": score}

    if abs(delta) < min_delta_rpm:
        warn_txt = "" if level == "normal" else "  (đang có dấu hiệu bất thường)"
        return {"state": "normal",
                "text": f"Hệ thống đang chạy đúng vùng tối ưu — giữ nguyên "
                        f"setpoint {speed}.{warn_txt}",
                "detail": detail, "speed": speed, "level": level, "score": score}

    huong = "tăng" if delta > 0 else "giảm"
    text = (f"Đề xuất {huong} setpoint về {speed} (Δ {delta:+.1f}) "
            f"để bám tốc độ mục tiêu mà vẫn giữ dòng điện trong giới hạn.")
    return {"state": "suggest", "text": text, "detail": detail, "speed": speed,
            "level": level, "score": score}


def find_artifact_dir():
    """Tìm artifact: biến môi trường > thư mục gốc app (dev) > /usr/share."""
    env = os.environ.get("IHCS_ARTIFACT_DIR")
    if env:
        return env
    local = Path(__file__).resolve().parents[1] / "artifact"
    if (local / "manifest.json").exists():
        return str(local)
    return DEFAULT_ARTIFACT_DIR


__all__ = ["ObservationBuilder", "IHCSAdvisor", "format_advisory",
           "anomaly_level", "find_artifact_dir", "DEFAULT_ARTIFACT_DIR"]


if __name__ == "__main__":
    # Chạy thử nhanh: python3 services/ihcs_bridge.py [artifact_dir]
    advisor = IHCSAdvisor(sys.argv[1] if len(sys.argv) > 1 else find_artifact_dir())
    ok = advisor.load()
    print(f"artifact : {advisor.artifact_dir}")
    print(f"mode     : {advisor.mode} (version {advisor.artifact_version})")
    if advisor.error:
        print(f"ghi chú  : {advisor.error}")
    if not ok:
        sys.exit(1)

    # Model cần 50 mẫu liên tiếp @1 Hz mới chấm điểm được, nên phải mồi cửa sổ
    # trước khi chạy advisory — điểm vận hành lấy theo rig thật (thanh ghi lệnh
    # 3854 ~ 971 rpm ở rail 24,8 V).
    builder = advisor.make_observation_builder()
    for i in range(60):
        obs = builder.update(speed_rpm=971.0, voltage_v=24.8, current_a=0.046,
                             cmd_register=3854, ts=float(i))
        advisor.observe(obs, ts=float(i))
    print(json.dumps(advisor.run(obs, ts=60.0), indent=2, ensure_ascii=False))
