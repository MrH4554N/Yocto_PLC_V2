# Model Card: ihcs_raspi_policy v0.1.0

## Overview
IHCS Raspberry Pi advisory policy package.
Target device: raspberry_pi

## Safety
- Mode: advisory_only
- Control role: mpc_recommends_pid_setpoint
- Human approval required: True
- PLC write allowed: False

## Models
| Component | Purpose |
|-----------|---------|
| mpc/plant_model.npz | Discrete LTI state-space model (A, B, C, D, x_eq, u_eq) |
| mpc/cost_weights.json | Q, R, ρ_I, ρ_T |
| mpc/constraints.json | u_min, u_max, du_min, du_max, I_max, T_max |
| mpc/horizon_config.json | Prediction horizon N, dt |
| mpc/safety_envelope.json | Runtime clipping/blocking envelope (defense-in-depth) |
| lstm_anomaly/model.onnx | Anomaly detection (reconstruction) |

## MPC Output
The MPC outputs **recommended_delta_setpoint_rpm** only.
It does NOT output PWM, voltage, current, torque, or any PLC register value.
All outputs require human approval before application.

## Intended Use
Phase 2 advisory-only runtime on Raspberry Pi. Operator reviews recommendations.
No autonomous PLC writes are performed.

## Out of Scope
- Direct motor control
- Autonomous PLC register modification
- Real-time closed-loop control without human oversight
