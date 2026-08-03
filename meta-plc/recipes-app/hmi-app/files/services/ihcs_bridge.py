#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cầu nối giữa telemetry của HMI và runtime advisory IHCS.

HMI chỉ đo được 3 đại lượng: tốc độ (D120 qua Modbus), điện áp và dòng điện
(INA219/INA226 qua I2C). Artifact IHCS lại cần đủ 12 feature theo
``preprocessing/feature_list.json``. Module này lấp khoảng trống đó:

  • ObservationBuilder — dựng 12 feature từ 3 phép đo + setpoint hiện hành,
    dùng đúng công thức của Phase_1 ``preprocessing/derive_signals.py`` để
    dữ liệu suy luận trùng phân phối với dữ liệu huấn luyện.
  • IHCSAdvisor       — nạp artifact, chạy advisory, tự hạ cấp xuống chế độ
    chỉ-phát-hiện-bất-thường nếu image thiếu osqp/scipy (phần MPC).
  • format_advisory   — đổi advisory JSON thành chuỗi hiển thị cho HMI.

Chế độ advisory-only được giữ nguyên: module này KHÔNG ghi PLC.
"""

import json
import math
import os
import time
from pathlib import Path

import numpy as np

DEFAULT_ARTIFACT_DIR = os.environ.get(
    "IHCS_ARTIFACT_DIR", "/usr/share/hmi-app/artifact")

RPM_TO_RAD_S = 2.0 * math.pi / 60.0
_EPS_POWER_W = 1e-3

# Mặc định của derive_signals.py khi system_parameters không khai báo
DEFAULT_ERROR_INTEGRAL_TAU_S = 60.0
DEFAULT_ERROR_INTEGRAL_CLAMP_S = 100.0


# ==========================================================================
# DỰNG OBSERVATION
# ==========================================================================
class ObservationBuilder:
    """Suy ra 12 feature của artifact từ telemetry thô của HMI.

    Gọi update() mỗi chu kỳ đọc phần cứng (không phải mỗi chu kỳ AI) — bộ tích
    phân sai số và mô hình nhiệt là hệ động học theo thời gian, bỏ mẫu sẽ làm
    lệch giá trị.
    """

    def __init__(self, system_parameters: dict):
        motor = system_parameters.get("motor", {})
        sim = system_parameters.get("simulation", {})

        self.kt = float(motor.get("Kt", 0.1736))
        self.i_no_load = float(motor.get("no_load_current_a", 0.02))
        self.rated_speed = float(motor.get("rated_speed_rpm", 660.0))

        # Không có cảm biến nhiệt trên phần cứng này: temp_c là ước lượng I^2R,
        # đúng như cách tập huấn luyện sinh ra nó (signal_registry.json ghi
        # source_method = thermal_estimate_i2r, quality_flag = 2).
        self.ambient_temp_c = float(sim.get("ambient_temp_c", 28.0))
        self.r_winding = float(sim.get("winding_resistance_ohm", 20.0))
        self.r_thermal = float(sim.get("thermal_resistance_c_per_w", 15.0))
        self.c_thermal = float(sim.get("thermal_mass_j_per_c", 30.0))

        self.tau_integral = float(
            system_parameters.get("error_integral_tau_s",
                                  DEFAULT_ERROR_INTEGRAL_TAU_S))
        self.clamp_integral = float(
            system_parameters.get("error_integral_clamp_s",
                                  DEFAULT_ERROR_INTEGRAL_CLAMP_S)) * self.rated_speed

        self.default_dt = float(sim.get("dt", 1.0)) or 1.0

        # --- trạng thái tích lũy ---
        self.temp_c = self.ambient_temp_c
        self.error_integral = 0.0
        self.prev_speed = None
        self.prev_ts = None
        self.n_samples = 0

    def reset(self):
        self.temp_c = self.ambient_temp_c
        self.error_integral = 0.0
        self.prev_speed = None
        self.prev_ts = None
        self.n_samples = 0

    def update(self, speed_rpm, voltage_v, current_a, setpoint_rpm, ts=None):
        """Cập nhật một mẫu telemetry, trả về observation đầy đủ 12 feature."""
        ts = time.monotonic() if ts is None else float(ts)
        dt = self.default_dt if self.prev_ts is None else max(ts - self.prev_ts, 1e-3)
        self.prev_ts = ts

        speed = float(speed_rpm)
        voltage = float(voltage_v)
        current = float(current_a)
        setpoint = float(setpoint_rpm)

        # --- sai số bám và tích phân rò (leaky) ---
        tracking_error = setpoint - speed
        decay = math.exp(-dt / self.tau_integral) if self.tau_integral > 0 else 0.0
        self.error_integral = max(
            -self.clamp_integral,
            min(self.clamp_integral,
                self.error_integral * decay + tracking_error * dt))

        # --- gia tốc ---
        accel = 0.0 if self.prev_speed is None else (speed - self.prev_speed) / dt
        self.prev_speed = speed

        # --- mô-men ước lượng từ dòng ---
        torque = self.kt * max(current - self.i_no_load, 0.0)

        # --- công suất điện / cơ / hiệu suất ---
        power = voltage * current
        mech_power = torque * speed * RPM_TO_RAD_S
        efficiency = max(0.0, min(1.0, mech_power / max(power, _EPS_POWER_W)))

        # --- ước lượng nhiệt I^2R (không có cảm biến thật) ---
        # Hằng số thời gian nhiệt R_th*C_th = 450 s, nên nếu khởi tạo ở nhiệt độ
        # môi trường thì mất ~15 phút sau khi bật máy giá trị mới hội tụ. Suốt
        # quãng đó temp_c thấp hơn phân phối lúc train vài sigma và tự sinh ra
        # bất thường giả. Mẫu đầu tiên vì vậy khởi tạo thẳng ở điểm cân bằng
        # ứng với dòng đang đo được.
        p_heat = current * current * self.r_winding
        if self.n_samples == 0:
            self.temp_c = self.ambient_temp_c + p_heat * self.r_thermal
        else:
            p_cool = (self.temp_c - self.ambient_temp_c) / self.r_thermal
            self.temp_c += dt * (p_heat - p_cool) / self.c_thermal

        self.n_samples += 1

        return {
            "setpoint_rpm": setpoint,
            "speed_rpm": speed,
            "tracking_error_rpm": tracking_error,
            "current_a": current,
            "temp_c": self.temp_c,
            "voltage_v": voltage,
            "load_torque_est_nm": torque,
            "power_w": power,
            "mech_power_w": mech_power,
            "efficiency_est": efficiency,
            "accel_rpm_s": accel,
            "tracking_error_integral_rpm_s": self.error_integral,
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
            self._engine = _AnomalyOnlyEngine(loader)
            self._engine.load()
            self.mode = "anomaly_only"
            return True
        except Exception as e:
            self._engine = None
            self.mode = "unavailable"
            self.error = f"{type(e).__name__}: {e}"
            return False

    def run(self, observation):
        """Chạy một chu kỳ advisory. Trả về advisory JSON (dict)."""
        if self._engine is None:
            raise RuntimeError("advisor chưa nạp được artifact")
        return self._engine.run_advisory(observation)

    def make_observation_builder(self):
        return ObservationBuilder(self.system_parameters)


class _AnomalyOnlyEngine:
    """Engine rút gọn khi image chưa có osqp/scipy.

    Dùng lại đúng scaler + ONNX của artifact để tính điểm bất thường, nhưng
    không giải QP nên không đề xuất setpoint: advisory luôn bị chặn với
    block_reason="mpc_unavailable". Giữ nguyên định dạng advisory để HMI và
    format_advisory() không cần biết đang chạy chế độ nào.
    """

    def __init__(self, loader):
        self._loader = loader
        self._manifest = loader.manifest
        self._features = []
        self._mean = None
        self._scale = None
        self._thresholds = {}
        self._window_size = 50
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
                "lstm_anomaly/window_config.json").get("window_size", 50))
        except FileNotFoundError:
            pass

        import onnxruntime as ort
        self._session = ort.InferenceSession(
            self._loader.model_path("lstm_anomaly/model.onnx"))

    def run_advisory(self, observation):
        from datetime import datetime, timezone

        raw = np.array([float(observation.get(f, 0.0)) for f in self._features],
                       dtype=np.float32)
        scaled = (raw - self._mean) / self._scale
        window = np.tile(scaled, (self._window_size, 1)).reshape(
            1, self._window_size, len(self._features)).astype(np.float32)

        try:
            out = self._session.run(
                None, {self._session.get_inputs()[0].name: window})
            anomaly_score = float(np.mean((window - out[0]) ** 2))
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
            "current_state": {k: observation.get(k) for k in [
                "setpoint_rpm", "speed_rpm", "tracking_error_rpm",
                "current_a", "temp_c", "voltage_v", "load_torque_est_nm",
            ]},
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
                "lstm_anomaly_score": (round(anomaly_score, 6)
                                       if anomaly_score is not None else None),
                "anomaly_threshold": warning,
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
    """'normal' | 'warning' | 'critical' | 'unknown' theo ngưỡng của artifact."""
    ev = advisory.get("model_evidence", {})
    score = ev.get("lstm_anomaly_score")
    warning = ev.get("anomaly_threshold")
    if score is None:
        return "unknown"
    envelope = advisory.get("safety", {}).get("safety_envelope")
    reason = (advisory.get("recommendation", {}).get("block_reason") or "")
    if envelope == "blocked" and reason.startswith("anomaly_score"):
        return "critical"
    if warning is not None and score >= warning:
        return "warning"
    return "normal"


def format_advisory(advisory, speed_max=600, min_delta_rpm=1.0):
    """Đổi advisory JSON thành thứ HMI hiển thị được.

    Trả về dict:
      state  — "suggest" (cần phê duyệt) | "normal" | "blocked"
      text   — nội dung chính
      detail — dòng phụ (điểm bất thường, độ tin cậy, trạng thái solver)
      speed  — setpoint đề xuất đã làm tròn/kẹp biên, None nếu không có
    """
    rec = advisory.get("recommendation", {})
    ev = advisory.get("model_evidence", {})
    level = anomaly_level(advisory)

    score = ev.get("lstm_anomaly_score")
    warn = ev.get("anomaly_threshold")
    score_txt = ("bất thường %.4f / ngưỡng %.4f" % (score, warn)
                 if score is not None and warn is not None
                 else "bất thường: không có dữ liệu")

    block_reason = rec.get("block_reason")
    if block_reason:
        if block_reason == "mpc_unavailable":
            text = ("Chưa chạy được bộ tối ưu MPC (image thiếu osqp/scipy).\n"
                    "AI chỉ giám sát bất thường, không đề xuất setpoint.")
        elif block_reason.startswith("anomaly_score"):
            text = ("CẢNH BÁO: dữ liệu vận hành lệch xa vùng bình thường.\n"
                    "AI chặn mọi đề xuất — kiểm tra băng tải, tải trọng và nguồn điện.")
        else:
            text = ("Không tạo được đề xuất an toàn ở chu kỳ này.\n"
                    f"Lý do: {block_reason}")
        return {"state": "blocked", "text": text,
                "detail": f"{score_txt}   •   {block_reason}", "speed": None}

    setpoint = rec.get("recommended_setpoint_rpm")
    delta = rec.get("recommended_delta_setpoint_rpm") or 0.0
    if setpoint is None:
        return {"state": "blocked",
                "text": "Không có đề xuất ở chu kỳ này.",
                "detail": score_txt, "speed": None}

    speed = int(round(max(0.0, min(float(speed_max), float(setpoint)))))
    confidence = rec.get("confidence")
    conf_txt = f"độ tin cậy {confidence * 100:.0f}%" if confidence is not None else ""
    solver = ev.get("mpc_solver_status", "?")
    detail = f"{score_txt}   •   {conf_txt}   •   MPC: {solver}"

    if abs(delta) < min_delta_rpm:
        warn_txt = "" if level == "normal" else "  (đang có dấu hiệu bất thường)"
        return {"state": "normal",
                "text": f"Hệ thống đang chạy đúng vùng tối ưu — giữ nguyên "
                        f"setpoint {speed}.{warn_txt}",
                "detail": detail, "speed": speed}

    huong = "tăng" if delta > 0 else "giảm"
    text = (f"Đề xuất {huong} setpoint về {speed} (Δ {delta:+.1f}) "
            f"để bám tốc độ mục tiêu mà vẫn giữ dòng và nhiệt trong giới hạn.")
    return {"state": "suggest", "text": text, "detail": detail, "speed": speed}


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
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    advisor = IHCSAdvisor(sys.argv[1] if len(sys.argv) > 1 else find_artifact_dir())
    ok = advisor.load()
    print(f"artifact : {advisor.artifact_dir}")
    print(f"mode     : {advisor.mode} (version {advisor.artifact_version})")
    if advisor.error:
        print(f"ghi chú  : {advisor.error}")
    if not ok:
        sys.exit(1)
    builder = advisor.make_observation_builder()
    obs = builder.update(speed_rpm=651.0, voltage_v=11.596,
                         current_a=0.147, setpoint_rpm=660.0)
    print(json.dumps(advisor.run(obs), indent=2, ensure_ascii=False))
