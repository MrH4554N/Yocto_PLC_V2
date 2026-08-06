# Model Card: ihcs_raspi_policy v0.1.0

## Overview
IHCS Raspberry Pi advisory policy package.
Target device: raspberry_pi

Trained on **measured rig data** (`ai_training_data4.csv`, 42 815 raw rows →
27 688 samples @ 1 Hz, 7.70 h) — not on simulator output. The bench rig is an
open-loop DC conveyor drive: the PLC command register drives motor **voltage**,
saturating at the measured 24.8 V supply rail.

## Safety
- Mode: advisory_only
- Control role: mpc_recommends_pid_setpoint
- Human approval required: True
- PLC write allowed: False

## Models
| Component | Purpose |
|-----------|---------|
| mpc/plant_model.npz | Discrete LTI state-space model (A, B, C, D, x_eq, u_eq) — states `[speed_rpm, current_lp15_a]`, input `voltage_v`, output `speed_rpm`, dt = 1 s |
| mpc/cost_weights.json | Q, R, ρ_I (no thermal state ⇒ no ρ_T) |
| mpc/constraints.json | u_min, u_max, du_min, du_max in **volts**; I_max on `current_lp15_a` |
| mpc/horizon_config.json | Prediction horizon N = 20, dt = 1 s |
| mpc/safety_envelope.json | Runtime clipping/blocking envelope in RPM (defense-in-depth) |
| lstm_anomaly/model.onnx | Anomaly detection — 49 input steps × 10 features → predicted step 50 |
| preprocessing/command_calibration.json | Command register → RPM / volts lookup (13 measured anchors) |

## Inputs
Ten features, fixed order (`preprocessing/feature_list.json`), all derived from
four measured channels — `speed_rpm` (D120), `voltage_v` + `current_a`
(INA219/INA226) and the command register (D8116):

    setpoint_rpm, speed_rpm, voltage_v, current_a, current_lp15_a,
    tracking_error_rpm, accel_rpm_s, power_w, speed_per_volt_rpm_v,
    current_ripple_a

`current_lp15_a` and `current_ripple_a` use a **trailing** 15 s window (mean and
sample standard deviation) — past samples only, exactly as at training time.
There is no temperature sensor on this hardware and no thermal feature: the
previous 12-feature list (with `temp_c`, `load_torque_est_nm`, `mech_power_w`,
`efficiency_est`, `tracking_error_integral_rpm_s`) does **not** apply to this
model.

The command register controls voltage and saturates at ~3314; converting it with
a linear gain is wrong. Always go through `command_calibration.json`. Without the
register the runtime degrades to `setpoint_rpm = voltage_v × rpm_per_volt`, which
still catches mechanical faults but no longer detects command-tracking faults.

## Anomaly scoring
Reconstruction MSE between the predicted 50th step and the measured one.
Thresholds learnt on the validation split (`lstm_anomaly/thresholds.json`):
warning = 0.5168 (p95), critical = 0.9235 (p99), val mean MSE = 0.3475.

Measured on the held-out test split with 15 synthetic injected faults:
warning precision 0.871 / recall 0.769, critical precision 0.968 / recall 0.655,
fault-to-normal MSE ratio 52.4×. **The faults are synthetic** — no real fault has
ever been recorded on this rig, so these numbers are not hardware-validated.

## MPC Output
The MPC solves in volts and the runtime converts the solution to
**recommended_delta_setpoint_rpm** using `rpm_per_volt` = 39.2742.
It does NOT output PWM, current, torque, or any PLC register value.
All outputs require human approval before application.

## Intended Use
Phase 2 advisory-only runtime on Raspberry Pi. Operator reviews recommendations.
No autonomous PLC writes are performed.

## Out of Scope
- Direct motor control
- Autonomous PLC register modification
- Real-time closed-loop control without human oversight
