"""Phase 2 advisory inference engine.

Runs LSTM anomaly detection (via ONNX Runtime) and a Linear MPC setpoint
recommendation (via osqp). Produces advisory JSON conforming to
``shared/contracts/advisory_contract.md`` plus the MPC additions in
``shared/contracts/mpc_contract.md``.

Safety invariants (never overrideable):
  mode = "advisory_only"
  safety.human_approval_required = true
  safety.autonomous_action = false
  safety.plc_write_allowed = false
  safety.plc_write_performed = false
  operator_action_required = true

Invariant 15: when the MPC QP fails to solve, the advisory must be blocked
with ``block_reason`` set; never propagate a stale recommendation.

Two things about the current artifact drive the shape of this module:

* The LSTM is a **next-step predictor**, not a whole-window autoencoder: it
  takes ``window_size`` consecutive samples and predicts the one after them.
  The anomaly score is the MSE between that prediction and the sample that
  actually arrived, so the engine has to keep a rolling window of real
  history — a single observation cannot be scored on its own.
* The MPC plant is ``[speed_rpm, current_lp15_a]`` driven by **voltage**.
  The QP therefore solves in volts and the answer is converted to the
  operator-facing RPM setpoint with ``rpm_per_volt`` before the safety
  envelope (whose bounds are in RPM) sees it.
"""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime, timezone

import numpy as np

try:
    import onnxruntime as ort
    _ORT_AVAILABLE = True
except ImportError:
    _ORT_AVAILABLE = False

from .artifact_loader import ArtifactLoader
from .mpc_controller import MPCController
from .safety_envelope import SafetyEnvelope


# Sampling period of the training data. The window must span the same amount of
# wall-clock time it did at training time, so samples arriving faster than this
# are used to update the caller's filters but not admitted to the window.
DEFAULT_SAMPLE_PERIOD_S = 1.0

# Signals echoed back to the operator/MQTT alongside the recommendation.
CURRENT_STATE_KEYS = [
    "setpoint_rpm", "speed_rpm", "tracking_error_rpm",
    "current_a", "current_lp15_a", "voltage_v", "power_w",
]


class InferenceEngine:
    def __init__(self, artifact_loader: ArtifactLoader):
        self._loader = artifact_loader
        self._manifest = artifact_loader.manifest
        self._feature_list: list[str] = []
        self._scaler_params: dict = {}
        self._anomaly_window_config: dict = {}
        self._anomaly_thresholds: dict = {}
        self._safety_envelope: SafetyEnvelope | None = None
        self._anomaly_session = None
        self._mpc: MPCController | None = None
        self._loaded = False
        # Cached scaler arrays (built once in load())
        self._scaler_mean: np.ndarray | None = None
        self._scaler_scale: np.ndarray | None = None
        self._scaler_data_min: np.ndarray | None = None
        self._scaler_data_range: np.ndarray | None = None
        # Rolling window of scaled samples: window_size inputs + 1 target
        self._window: deque = deque()
        self._window_size = 0
        self._sample_period_s = DEFAULT_SAMPLE_PERIOD_S
        self._last_admit_ts: float | None = None
        self.rpm_per_volt = 0.0

    def load(self) -> None:
        self._feature_list = _normalize_feature_list(
            self._loader.load_json("preprocessing/feature_list.json")
        )
        self._scaler_params = self._loader.load_json("preprocessing/scaler.json")

        scaler_features = _normalize_feature_list(self._scaler_params)
        if scaler_features and scaler_features != self._feature_list:
            raise ValueError(
                "scaler.json feature order differs from feature_list.json — "
                "model and scaler are not from the same training run:\n"
                f"  feature_list: {self._feature_list}\n"
                f"  scaler      : {scaler_features}"
            )

        try:
            self._anomaly_window_config = self._loader.load_json("lstm_anomaly/window_config.json")
        except FileNotFoundError:
            self._anomaly_window_config = {}

        try:
            self._anomaly_thresholds = self._loader.load_json("lstm_anomaly/thresholds.json")
        except FileNotFoundError:
            self._anomaly_thresholds = {}

        # Build scaler arrays once so _build_feature_vector() doesn't re-allocate per call
        n = len(self._feature_list)
        method = self._scaler_params.get("method", "standard")
        if method == "standard":
            mean = np.array(_scaler_value(self._scaler_params, "mean", n, 0.0), dtype=np.float32)
            scale = np.array(_scaler_value(self._scaler_params, "scale", n, 1.0), dtype=np.float32)
            self._scaler_mean = mean
            self._scaler_scale = np.where(scale == 0, 1.0, scale)
        elif method == "minmax":
            data_min = np.array(_scaler_value(self._scaler_params, "data_min", n, 0.0), dtype=np.float32)
            data_range = np.array(_minmax_range(self._scaler_params, n), dtype=np.float32)
            self._scaler_data_min = data_min
            self._scaler_data_range = np.where(data_range == 0, 1.0, data_range)

        # ----- Rolling window for the next-step predictor -----
        # window_size counts INPUT steps; one more slot holds the sample the
        # prediction is scored against.
        self._window_size = int(self._anomaly_window_config.get("window_size", 49))
        self._window = deque(maxlen=self._window_size + 1)

        system_parameters = self._load_optional_json("preprocessing/system_parameters.json")
        period_ms = system_parameters.get("sampling", {}).get("resample_period_ms")
        if period_ms:
            self._sample_period_s = float(period_ms) / 1000.0

        # ----- Volts → RPM for the operator-facing recommendation -----
        self.rpm_per_volt = _resolve_rpm_per_volt(
            system_parameters,
            self._load_optional_json("preprocessing/command_calibration.json"),
        )

        # ----- MPC controller (replaces the deprecated PPO path) -----
        # The MPC config lives under mpc/ in the artifact bundle. The
        # safety_envelope.json file is still under mpc/ (a separate concept
        # from the QP constraints — it is the runtime *clipping/blocking*
        # envelope applied AFTER the MPC solution, as defense-in-depth).
        plant_path = self._loader.model_path("mpc/plant_model.npz")
        cost_path = self._loader.model_path("mpc/cost_weights.json")
        cons_path = self._loader.model_path("mpc/constraints.json")
        hor_path = self._loader.model_path("mpc/horizon_config.json")
        self._mpc = MPCController(plant_path, cost_path, cons_path, hor_path)

        envelope_cfg = self._loader.load_json("mpc/safety_envelope.json")
        self._safety_envelope = SafetyEnvelope(envelope_cfg, self._anomaly_thresholds)

        if _ORT_AVAILABLE:
            try:
                anomaly_path = self._loader.model_path("lstm_anomaly/model.onnx")
                self._anomaly_session = ort.InferenceSession(anomaly_path)
            except Exception:
                self._anomaly_session = None
            _check_model_width(self._anomaly_session, len(self._feature_list))

        self._loaded = True

    # ------------------------------------------------------------------
    # Rolling window
    # ------------------------------------------------------------------

    def observe(self, observation: dict[str, float], ts: float | None = None) -> bool:
        """Offer one sample to the anomaly window. Returns True if admitted.

        Call this every acquisition cycle, not only on advisory ticks: the
        window has to hold real consecutive history for the predictor to mean
        anything. Samples arriving faster than the training sample period are
        dropped here (the caller's own filters still see them), so a 2 Hz
        acquisition loop still produces a window spanning the same 49 s it did
        at training time.
        """
        if not self._loaded:
            raise RuntimeError("load() must be called before observe()")

        ts = time.monotonic() if ts is None else float(ts)
        if (self._last_admit_ts is not None
                and (ts - self._last_admit_ts) < self._sample_period_s * 0.98):
            return False

        vec = self._build_feature_vector(observation)
        if not np.all(np.isfinite(vec)):
            # One bad channel must not poison the next 49 s of window.
            return False

        self._last_admit_ts = ts
        self._window.append(vec)
        return True

    @property
    def warmup_remaining(self) -> int:
        """Samples still needed before an anomaly score can be produced."""
        return max(0, self._window_size + 1 - len(self._window))

    def reset_window(self) -> None:
        self._window.clear()
        self._last_admit_ts = None

    # ------------------------------------------------------------------

    def run_advisory(self, observation: dict[str, float], ts: float | None = None) -> dict:
        """Run inference on a single observation dict (canonical signal names → float).

        Returns advisory JSON conforming to ``advisory_contract.md`` (with the
        MPC-specific ``model_evidence`` keys defined in ``mpc_contract.md``).
        Safety fields are always set correctly regardless of solver outcome.
        """
        if not self._loaded:
            raise RuntimeError("load() must be called before run_advisory()")

        # Harmless if the caller already fed this sample through observe():
        # the sample-period gate admits it at most once.
        self.observe(observation, ts=ts)

        ts_utc = datetime.now(timezone.utc).isoformat()

        # Anomaly score over the accumulated window (None until it is full)
        anomaly_score = self._compute_anomaly_score()
        warning_threshold = self._anomaly_thresholds.get("warning_threshold")
        critical_threshold = self._anomaly_thresholds.get("critical_threshold")

        # MPC recommendation. The plant is driven by voltage, so the previous
        # input is the voltage currently across the motor, and the states are
        # measured speed plus the 15 s filtered current.
        current_setpoint = float(observation.get("setpoint_rpm", 0.0))
        x0 = np.array([
            float(observation.get("speed_rpm", 0.0)),
            float(observation.get("current_lp15_a", observation.get("current_a", 0.0))),
        ], dtype=np.float64)
        u_prev = float(observation.get("voltage_v", 0.0))
        # The reference is whatever speed the operator has currently commanded —
        # the MPC's job is to take a smooth path TO that reference while
        # respecting the current constraint. In v1 the reference is the current
        # setpoint; M4 may extend to operator-supplied targets.
        r_ref = current_setpoint
        mpc_result = self._mpc.compute(x0=x0, r=r_ref, u_prev=u_prev)

        mpc_status = mpc_result["status"]
        mpc_block_reason = mpc_result["block_reason"]
        recommended_voltage = mpc_result.get("u_next")

        # --- Invariant 15: MPC infeasibility → fail-safe ---
        if mpc_block_reason is not None:
            recommendation = {
                "type": "pid_setpoint_recommendation",
                "recommended_delta_setpoint_rpm": None,
                "recommended_setpoint_rpm": None,
                "confidence": 0.0,
                "block_reason": mpc_block_reason,
            }
            envelope_state = "blocked"
        else:
            # The QP answers in volts; the operator commands RPM. Convert with
            # the measured rpm_per_volt before the RPM-denominated envelope.
            raw_setpoint = float(recommended_voltage) * self.rpm_per_volt
            raw_delta = raw_setpoint - current_setpoint

            envelope_result = self._safety_envelope.apply(
                raw_delta=raw_delta,
                current_setpoint=current_setpoint,
                anomaly_score=anomaly_score,
            )
            envelope_state = envelope_result["state"]

            if envelope_state == "blocked":
                recommendation = {
                    "type": "pid_setpoint_recommendation",
                    "recommended_delta_setpoint_rpm": None,
                    "recommended_setpoint_rpm": None,
                    "confidence": 0.0,
                    "block_reason": envelope_result.get("block_reason"),
                }
            else:
                recommendation = {
                    "type": "pid_setpoint_recommendation",
                    "recommended_delta_setpoint_rpm": round(
                        envelope_result["delta_setpoint_rpm"], 4),
                    "recommended_setpoint_rpm": round(
                        envelope_result["recommended_setpoint_rpm"], 4),
                    "confidence": self._estimate_confidence(
                        anomaly_score, warning_threshold, mpc_status),
                }

        advisory = {
            "timestamp_utc": ts_utc,
            "mode": "advisory_only",
            "system_id": "ihcs_servo_conveyor",
            "current_state": {k: observation.get(k) for k in CURRENT_STATE_KEYS},
            "recommendation": recommendation,
            "model_evidence": {
                "mpc_controller_version": self._manifest.get("artifact_version", "unknown"),
                "mpc_solver_status": mpc_status,
                "mpc_iterations": mpc_result.get("iterations"),
                "mpc_solve_ms": round(mpc_result.get("solve_ms", 0.0), 3),
                "mpc_recommended_voltage_v": _safe_round(recommended_voltage, 4),
                "mpc_slack_violation_current_a": _safe_round(
                    mpc_result.get("slack_violation_current_a"), 6),
                "lstm_anomaly_score": round(anomaly_score, 6) if anomaly_score is not None else None,
                "anomaly_threshold": warning_threshold,
                "anomaly_critical_threshold": critical_threshold,
                "anomaly_warmup_remaining": self.warmup_remaining,
            },
            "safety": {
                "safety_envelope": envelope_state,
                "human_approval_required": True,
                "autonomous_action": False,
                "plc_write_performed": False,
                "plc_write_allowed": False,
            },
            "rag_context": {
                "status": "not_configured",
                "sources": [],
            },
            "operator_action_required": True,
        }
        return advisory

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_optional_json(self, rel_path: str) -> dict:
        try:
            return self._loader.load_json(rel_path)
        except FileNotFoundError:
            return {}

    def _build_feature_vector(self, observation: dict[str, float]) -> np.ndarray:
        if not self._feature_list:
            return np.zeros((1,), dtype=np.float32)

        raw = np.array([observation.get(f, 0.0) for f in self._feature_list], dtype=np.float32)
        method = self._scaler_params.get("method", "standard")

        if method == "standard" and self._scaler_mean is not None:
            return (raw - self._scaler_mean) / self._scaler_scale
        elif method == "minmax" and self._scaler_data_min is not None:
            return (raw - self._scaler_data_min) / self._scaler_data_range
        return raw

    def _compute_anomaly_score(self) -> float | None:
        """MSE between the predicted next step and the one actually measured."""
        if not _ORT_AVAILABLE or self._anomaly_session is None:
            return None
        if len(self._window) <= self._window_size:
            return None

        window = np.stack(list(self._window))              # (window_size+1, n_features)
        inputs = window[:-1][None, :, :].astype(np.float32)
        target = window[-1]

        input_name = self._anomaly_session.get_inputs()[0].name
        try:
            outputs = self._anomaly_session.run(None, {input_name: inputs})
            prediction = np.asarray(outputs[0], dtype=np.float32).reshape(-1)
            return float(np.mean((prediction - target) ** 2))
        except Exception:
            return None

    def _estimate_confidence(
        self,
        anomaly_score: float | None,
        warning_threshold: float | None,
        mpc_status: str,
    ) -> float:
        # ``solved_inaccurate`` knocks confidence down a notch even if the
        # safety envelope accepts the recommendation.
        base = 0.85 if mpc_status == "solved inaccurate" else 1.0
        if anomaly_score is None or warning_threshold is None or warning_threshold == 0:
            return round(base * 0.5, 4)
        ratio = anomaly_score / warning_threshold
        confidence = base * max(0.0, min(1.0, 1.0 - ratio))
        return round(confidence, 4)


def _normalize_feature_list(raw: object) -> list[str]:
    """Accept both current list format and older metadata-wrapped format."""
    if isinstance(raw, dict):
        raw = raw.get("features", [])
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw]


def _resolve_rpm_per_volt(system_parameters: dict, command_calibration: dict) -> float:
    """Steady-state RPM produced per volt across the motor.

    The MPC manipulates voltage but the operator commands RPM, so this factor
    is what makes the recommendation readable. It is measured, not assumed:
    fail loudly rather than invent one, otherwise every recommendation would be
    silently scaled wrong.
    """
    value = system_parameters.get("motor", {}).get("rpm_per_volt")
    if value is None:
        value = command_calibration.get("rpm_per_volt")
    if value is None:
        raise ValueError(
            "rpm_per_volt missing from both preprocessing/system_parameters.json "
            "and preprocessing/command_calibration.json — cannot convert the MPC "
            "voltage solution into an RPM setpoint recommendation"
        )
    return float(value)


def _check_model_width(session, n_features: int) -> None:
    """Guard against an ONNX file and a scaler from different training runs."""
    if session is None:
        return
    shape = session.get_inputs()[0].shape
    model_features = shape[-1] if shape else None
    if isinstance(model_features, int) and model_features != n_features:
        raise ValueError(
            f"model.onnx takes {model_features} features but the artifact "
            f"declares {n_features} — model and preprocessing config are not "
            "from the same training run"
        )


def _scaler_value(params: dict, base_key: str, n: int, default: float) -> list[float]:
    value = params.get(base_key)
    if value is None:
        value = params.get(f"{base_key}_")
    if value is None:
        return [default] * n
    return value


def _minmax_range(params: dict, n: int) -> list[float]:
    value = params.get("data_range")
    if value is not None:
        return value

    data_min = params.get("data_min", params.get("data_min_"))
    data_max = params.get("data_max", params.get("data_max_"))
    if data_min is not None and data_max is not None:
        return (np.array(data_max, dtype=np.float32) - np.array(data_min, dtype=np.float32)).tolist()

    scale = params.get("scale", params.get("scale_"))
    if scale is not None:
        scale_arr = np.array(scale, dtype=np.float32)
        scale_arr = np.where(scale_arr == 0, 1.0, scale_arr)
        return (1.0 / scale_arr).tolist()

    return [1.0] * n


def _safe_round(value, ndigits: int):
    if value is None:
        return None
    try:
        return round(float(value), ndigits)
    except (TypeError, ValueError):
        return None
