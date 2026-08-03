"""
Safety envelope for Phase 2 advisory outputs.

Clips or blocks recommendations that exceed configured limits.
Never modifies the mandatory safety fields (mode, human_approval_required, etc.).
"""

import json
from pathlib import Path


class SafetyEnvelope:
    """
    Applies the safety envelope to PPO recommendations.

    States:
      pass    — recommendation is within bounds; output unchanged
      clipped — recommendation was clipped to the configured delta bounds
      blocked — recommendation was blocked (e.g. anomaly score too high)
    """

    def __init__(self, safety_envelope_config: dict, thresholds: dict | None = None):
        """
        safety_envelope_config: from ppo_setpoint/safety_envelope.json
        thresholds: from lstm_anomaly/thresholds.json (optional)
        """
        self._cfg = safety_envelope_config
        self._thresholds = thresholds or {}

    @classmethod
    def from_artifact(cls, artifact_loader) -> "SafetyEnvelope":
        cfg = artifact_loader.load_json("mpc/safety_envelope.json")
        try:
            thresholds = artifact_loader.load_json("lstm_anomaly/thresholds.json")
        except FileNotFoundError:
            thresholds = {}
        return cls(cfg, thresholds)

    def apply(
        self,
        raw_delta: float,
        current_setpoint: float,
        anomaly_score: float | None = None,
    ) -> dict:
        """
        Returns dict with keys:
          state: "pass" | "clipped" | "blocked"
          delta_setpoint_rpm: final delta (may be clipped)
          recommended_setpoint_rpm: current_setpoint + delta
          block_reason: str | None
        """
        # Check anomaly block condition
        if anomaly_score is not None:
            critical = self._thresholds.get("critical_threshold")
            if critical is not None and anomaly_score >= critical:
                return {
                    "state": "blocked",
                    "delta_setpoint_rpm": None,
                    "recommended_setpoint_rpm": None,
                    "block_reason": f"anomaly_score {anomaly_score:.4f} >= critical threshold {critical:.4f}",
                }

        # Clip delta to configured bounds
        action_bounds = self._cfg.get("action_bounds", {})
        min_delta = action_bounds.get("min_delta_setpoint_rpm", -200.0)
        max_delta = action_bounds.get("max_delta_setpoint_rpm", 200.0)

        clipped = False
        delta = raw_delta
        if delta < min_delta:
            delta = min_delta
            clipped = True
        elif delta > max_delta:
            delta = max_delta
            clipped = True

        recommended_setpoint = current_setpoint + delta

        # Clip recommended_setpoint to system limits
        setpoint_bounds = self._cfg.get("setpoint_bounds", {})
        min_sp = setpoint_bounds.get("min_setpoint_rpm")
        max_sp = setpoint_bounds.get("max_setpoint_rpm")
        if min_sp is not None and recommended_setpoint < min_sp:
            recommended_setpoint = min_sp
            delta = recommended_setpoint - current_setpoint
            clipped = True
        if max_sp is not None and recommended_setpoint > max_sp:
            recommended_setpoint = max_sp
            delta = recommended_setpoint - current_setpoint
            clipped = True

        return {
            "state": "clipped" if clipped else "pass",
            "delta_setpoint_rpm": delta,
            "recommended_setpoint_rpm": recommended_setpoint,
            "block_reason": None,
        }
