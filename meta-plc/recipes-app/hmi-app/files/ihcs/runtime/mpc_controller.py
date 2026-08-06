"""Linear Model Predictive Controller for the IHCS setpoint advisor.

Implements the contract in ``shared/contracts/mpc_contract.md``:

* Discrete-time LTI plant ``x_{k+1} = A x_k + B u_k`` (in deviation form,
  centred on the operating-point pair ``(x_eq, u_eq)`` produced by M1).
* Quadratic stage cost
  ``(y_k − r)^T Q (y_k − r) + Δu_k^T R Δu_k + ρ_I ε_I,k^2``.
* Hard input + rate bounds, soft upper bound on the filtered current.
* osqp 1.x as the QP solver, with warm-start across consecutive calls.

The plant identified on the bench rig (2026-08-05) has **two** states,
``[speed_rpm, current_lp15_a]``, and its manipulated variable is the motor
**voltage**, not a speed setpoint: the rig is open loop and the PLC command
register drives voltage. ``u_min``/``u_max``/``du_*`` in constraints.json are
therefore volts, and the caller passes/receives volts. There is no thermal
state on this hardware, so the temperature slack (``ρ_T``, ``T_max``) that the
previous 3-state model carried is gone — nothing measures temperature and
nothing can be predicted about it.

The QP is constructed once at startup (sparse matrices fixed for the lifetime
of the controller) and only the right-hand-side vectors ``q``, ``l``, ``u``
are refreshed each tick — that hits the < 10 ms budget on Raspberry Pi 4.

Invariant 15 (``shared/safety/safety_invariants.md``) is enforced here:
any non-``solved`` solver status is converted into a ``block_reason`` and
returned to the caller; never propose stale or partial solutions.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import osqp
import scipy.sparse as sp


# Match mpc_contract.md state ordering — the identifier saves these names in
# the .npz metadata; we re-check at load time so a model with reordered states
# triggers a clear error rather than a silent wrong-axis bug.
EXPECTED_STATE_NAMES = ["speed_rpm", "current_lp15_a"]
EXPECTED_INPUT_NAMES = ["voltage_v"]

# Index of the constrained state within the 2-state vector.
IDX_CURRENT = 1

# Map of osqp 1.x status strings to a single advisory ``block_reason`` token.
_BLOCK_REASON_MAP = {
    "primal infeasible": "mpc_primal_infeasible",
    "dual infeasible": "mpc_dual_infeasible",
    "primal infeasible inaccurate": "mpc_primal_infeasible",
    "dual infeasible inaccurate": "mpc_dual_infeasible",
    "max iter reached": "mpc_max_iter",
    "time limit reached": "mpc_time_limit",
    "non convex": "mpc_solver_error",
    "sigint": "mpc_solver_error",
    "solved inaccurate": None,        # treat as solved but with reduced confidence
}


class MPCSetupError(RuntimeError):
    """Raised when the MPC config files are inconsistent or missing."""


class MPCController:
    """Linear MPC for one advisory tick.

    Inputs to ``compute()`` are in **absolute** units; the controller handles
    the deviation-form transform internally.
    """

    def __init__(
        self,
        plant_model_path: str | Path,
        cost_weights_path: str | Path,
        constraints_path: str | Path,
        horizon_path: str | Path,
        osqp_settings: dict | None = None,
    ) -> None:
        self.plant_model_path = Path(plant_model_path)
        self.cost_weights_path = Path(cost_weights_path)
        self.constraints_path = Path(constraints_path)
        self.horizon_path = Path(horizon_path)

        self._load_plant_model()
        self._load_cost_weights()
        self._load_constraints()
        self._load_horizon()
        self._validate_dimensions()

        # Default solver settings (tuned for Pi 4 real-time budget)
        self._osqp_settings = {
            "eps_abs": 1e-4,
            "eps_rel": 1e-4,
            "max_iter": 4000,
            "verbose": False,
            "warm_starting": True,
            "polishing": False,
        }
        if osqp_settings:
            self._osqp_settings.update(osqp_settings)

        self._build_qp()

    # ------------------------------------------------------------------ load

    def _load_plant_model(self) -> None:
        if not self.plant_model_path.exists():
            raise MPCSetupError(f"plant model not found: {self.plant_model_path}")
        data = np.load(self.plant_model_path, allow_pickle=False)
        self.A = np.asarray(data["A"], dtype=np.float64)
        self.B = np.asarray(data["B"], dtype=np.float64)
        self.C = np.asarray(data["C"], dtype=np.float64)
        self.D = np.asarray(data["D"], dtype=np.float64)
        self.dt = float(data["dt"])
        self.x_eq = np.asarray(data["x_eq"], dtype=np.float64).flatten()
        self.u_eq = np.asarray(data["u_eq"], dtype=np.float64).flatten()
        meta_raw = data.get("identification_metadata", None)
        if meta_raw is not None:
            try:
                meta = json.loads(str(meta_raw))
                state_names = meta.get("state_names", EXPECTED_STATE_NAMES)
                input_names = meta.get("input_names", EXPECTED_INPUT_NAMES)
                if state_names != EXPECTED_STATE_NAMES:
                    raise MPCSetupError(
                        f"plant state order {state_names} != expected {EXPECTED_STATE_NAMES}; "
                        "re-identify the plant before deploying."
                    )
                if input_names != EXPECTED_INPUT_NAMES:
                    raise MPCSetupError(
                        f"plant input order {input_names} != expected {EXPECTED_INPUT_NAMES}"
                    )
                self.r2_below_threshold = bool(meta.get("r2_below_threshold", False))
            except json.JSONDecodeError:
                self.r2_below_threshold = False
        else:
            self.r2_below_threshold = False

    def _load_cost_weights(self) -> None:
        cfg = self._load_json(self.cost_weights_path, "cost_weights")
        self.Q = np.asarray(cfg["Q"], dtype=np.float64)
        self.R = np.asarray(cfg["R"], dtype=np.float64)
        self.rho_I = float(cfg["rho_I"])

    def _load_constraints(self) -> None:
        cfg = self._load_json(self.constraints_path, "constraints")

        def _f(key: str, default: float | None = None) -> float:
            val = cfg.get(key, default)
            if val is None or val == "[TBD]":
                if default is None:
                    raise MPCSetupError(f"constraints.{key} is [TBD] but has no fallback")
                return float(default)
            return float(val)

        # Defaults match the bench rig: u is the motor voltage, bounded by the
        # 24.8 V supply rail, and I_max is the soft limit on current_lp15_a.
        self.u_min = _f("u_min", 0.0)
        self.u_max = _f("u_max", 24.8)
        self.du_min = _f("du_min", -1.273)
        self.du_max = _f("du_max", 1.273)
        self.I_max = _f("I_max", 0.1)

    def _load_horizon(self) -> None:
        cfg = self._load_json(self.horizon_path, "horizon_config")
        self.N = int(cfg["N"])
        config_dt = float(cfg["dt"])
        if abs(config_dt - self.dt) > 1e-9:
            raise MPCSetupError(
                f"horizon_config.dt={config_dt} != plant_model.dt={self.dt}"
            )

    @staticmethod
    def _load_json(path: Path, name: str) -> dict:
        if not path.exists():
            raise MPCSetupError(f"{name} file not found: {path}")
        with open(path) as f:
            return json.load(f)

    def _validate_dimensions(self) -> None:
        n_x, n_u = self.A.shape[0], self.B.shape[1]
        if self.A.shape != (n_x, n_x):
            raise MPCSetupError(f"A has shape {self.A.shape}, expected ({n_x},{n_x})")
        if self.B.shape != (n_x, n_u):
            raise MPCSetupError(f"B has shape {self.B.shape}, expected ({n_x},{n_u})")
        if self.C.shape[1] != n_x:
            raise MPCSetupError(f"C cols {self.C.shape[1]} != n_x {n_x}")
        if self.D.shape[1] != n_u:
            raise MPCSetupError(f"D cols {self.D.shape[1]} != n_u {n_u}")
        if self.x_eq.shape != (n_x,):
            raise MPCSetupError(f"x_eq shape {self.x_eq.shape}, expected ({n_x},)")
        if self.u_eq.shape != (n_u,):
            raise MPCSetupError(f"u_eq shape {self.u_eq.shape}, expected ({n_u},)")
        if self.Q.shape != (self.C.shape[0], self.C.shape[0]):
            raise MPCSetupError(
                f"Q shape {self.Q.shape}, expected ({self.C.shape[0]},{self.C.shape[0]})"
            )
        if self.R.shape != (n_u, n_u):
            raise MPCSetupError(f"R shape {self.R.shape}, expected ({n_u},{n_u})")
        self.n_x = n_x
        self.n_u = n_u
        self.n_y = self.C.shape[0]
        if n_x < IDX_CURRENT + 1:
            raise MPCSetupError(
                f"plant has {n_x} states; need index {IDX_CURRENT} (current)"
            )

    # --------------------------------------------------------------- QP build

    def _build_qp(self) -> None:
        """Assemble the static parts of the QP (P, A_qp, l_static, u_static)."""
        N, nx, nu = self.N, self.n_x, self.n_u
        nv_x = nx * N
        nv_u = nu * N
        nv_eI = N
        nv = nv_x + nv_u + nv_eI
        self._nv = nv
        self._slices = {
            "x": slice(0, nv_x),
            "u": slice(nv_x, nv_x + nv_u),
            "eI": slice(nv_x + nv_u, nv),
        }

        # ----------------- Hessian H (z^T H z) and quadratic block P = 2H -----------------
        H = sp.lil_matrix((nv, nv), dtype=np.float64)

        # Cost on output tracking: each δx_{k} (for k=1..N) contributes C^T Q C
        CtQC = self.C.T @ self.Q @ self.C
        for k in range(N):
            i0 = k * nx
            H[i0:i0 + nx, i0:i0 + nx] += CtQC

        # Cost on Δu_k = δu_k - δu_{k-1}, k=0..N-1 (with δu_{-1} = δu_prev → linear term)
        # H[δu_k, δu_k] gets R from term k and from term k+1 (if k < N-1)
        # H[δu_k, δu_{k+1}] gets -R from term k+1
        u_base = nv_x
        for k in range(N):
            ik = u_base + k * nu
            H[ik:ik + nu, ik:ik + nu] += self.R
        for k in range(N - 1):
            ik = u_base + k * nu
            ikp1 = u_base + (k + 1) * nu
            H[ikp1:ikp1 + nu, ikp1:ikp1 + nu] += self.R
            # off-diagonal: cost = (δu_{k+1} - δu_k)^T R (δu_{k+1} - δu_k) →
            #   −2 δu_{k+1}^T R δu_k → off-diag block is -R (symmetric)
            H[ik:ik + nu, ikp1:ikp1 + nu] -= self.R
            H[ikp1:ikp1 + nu, ik:ik + nu] -= self.R

        # Slack penalty (diagonal)
        eI_base = nv_x + nv_u
        for k in range(N):
            H[eI_base + k, eI_base + k] += self.rho_I

        # OSQP wants (1/2) z^T P z + q^T z → P = 2H
        self._P = sp.csc_matrix(2.0 * H)

        # Pre-allocate q (linear term — filled per call)
        self._q = np.zeros(nv, dtype=np.float64)

        # ---------------- Constraint matrix A_qp and bounds (l, u) -----------------
        rows: list[sp.coo_matrix] = []
        l_list: list[np.ndarray] = []
        u_list: list[np.ndarray] = []

        # ----- (1) Dynamics equalities: δx_{k+1} - A δx_k - B δu_k = rhs_k -----
        # For k=0: I δx_1 - B δu_0 = A δx_0  → RHS = A·δx_0 (depends on x0; filled per call)
        # For k=1..N-1: I δx_{k+1} - A δx_k - B δu_k = 0
        for k in range(N):
            row = sp.lil_matrix((nx, nv), dtype=np.float64)
            ik1 = k * nx                                # δx_{k+1} columns (since k=0 → δx_1, etc.)
            row[:, ik1:ik1 + nx] = sp.eye(nx)
            if k >= 1:
                ik = (k - 1) * nx
                row[:, ik:ik + nx] = -self.A
            uk = u_base + k * nu
            row[:, uk:uk + nu] = -self.B
            rows.append(row.tocoo())
            l_list.append(np.zeros(nx))
            u_list.append(np.zeros(nx))   # equality → l == u; RHS for k=0 fixed per-call

        # ----- (2) Input bounds: u_min ≤ u_k ≤ u_max  → translate to δu  -----
        umin_dev = self.u_min - self.u_eq[0]
        umax_dev = self.u_max - self.u_eq[0]
        for k in range(N):
            row = sp.lil_matrix((1, nv), dtype=np.float64)
            row[0, u_base + k * nu] = 1.0
            rows.append(row.tocoo())
            l_list.append(np.array([umin_dev]))
            u_list.append(np.array([umax_dev]))

        # ----- (3) Rate bounds: du_min ≤ δu_k - δu_{k-1} ≤ du_max  -----
        # k=0: δu_0 - δu_prev (RHS fills per call via shift)
        # k=1..N-1: δu_k - δu_{k-1} ∈ [du_min, du_max] (static)
        for k in range(N):
            row = sp.lil_matrix((1, nv), dtype=np.float64)
            row[0, u_base + k * nu] = 1.0
            if k >= 1:
                row[0, u_base + (k - 1) * nu] = -1.0
            rows.append(row.tocoo())
            if k == 0:
                # placeholder; will be updated per-call to [du_min + δu_prev, du_max + δu_prev]
                l_list.append(np.array([self.du_min]))
                u_list.append(np.array([self.du_max]))
            else:
                l_list.append(np.array([self.du_min]))
                u_list.append(np.array([self.du_max]))

        # ----- (4) Soft current upper bound with slack -----
        # δx_k[idx] - ε ≤ I_max - x_eq[idx]  →  l = -∞, u = I_max - x_eq[idx]
        I_max_dev = self.I_max - self.x_eq[IDX_CURRENT]
        for k in range(N):
            ik1 = k * nx
            row = sp.lil_matrix((1, nv), dtype=np.float64)
            row[0, ik1 + IDX_CURRENT] = 1.0
            row[0, eI_base + k] = -1.0
            rows.append(row.tocoo())
            l_list.append(np.array([-np.inf]))
            u_list.append(np.array([I_max_dev]))

        # ----- (5) Slack non-negativity: ε ≥ 0 -----
        for k in range(N):
            row = sp.lil_matrix((1, nv), dtype=np.float64)
            row[0, eI_base + k] = 1.0
            rows.append(row.tocoo())
            l_list.append(np.array([0.0]))
            u_list.append(np.array([np.inf]))

        self._A_qp = sp.csc_matrix(sp.vstack(rows))
        self._l = np.concatenate(l_list).astype(np.float64)
        self._u = np.concatenate(u_list).astype(np.float64)

        # Index ranges for per-call RHS update
        self._dyn_row_start = 0
        self._dyn_row_end = N * nx
        self._rate_row_start = self._dyn_row_end + N        # after dyn + u bounds
        self._rate_row_k0 = self._rate_row_start            # row index of k=0 rate constraint

        # ----- OSQP setup -----
        self._solver = osqp.OSQP()
        self._solver.setup(
            self._P, self._q, self._A_qp, self._l, self._u,
            **self._osqp_settings,
        )
        self._first_solve = True

    # ----------------------------------------------------------------- solve

    def compute(self, x0: np.ndarray, r: float, u_prev: float) -> dict:
        """Solve the MPC QP and return ``{delta_u, u_next, status, ...}``.

        Parameters
        ----------
        x0:
            Current state ``[speed_rpm, current_lp15_a]``, in **absolute** units.
        r:
            Desired output (``speed_rpm``).
        u_prev:
            Previous applied input (``voltage_v``), absolute units.
        """
        x0 = np.asarray(x0, dtype=np.float64).flatten()
        if x0.shape != (self.n_x,):
            raise ValueError(
                f"x0 shape {x0.shape}, expected ({self.n_x},)"
            )

        delta_x0 = x0 - self.x_eq
        delta_u_prev = float(u_prev) - float(self.u_eq[0])
        r_dev = float(r) - float((self.C @ self.x_eq)[0])

        # --- Update linear term q ---
        q = np.zeros(self._nv)
        # Tracking gradient: −2 C^T Q r_dev applied to each δx_k (k=1..N)
        grad_x = -2.0 * (self.C.T @ self.Q @ np.array([r_dev])).flatten()
        for k in range(self.N):
            i0 = k * self.n_x
            q[i0:i0 + self.n_x] = grad_x
        # Rate coupling: cost (δu_0 − δu_prev)^T R (δu_0 − δu_prev) →
        #   gradient on δu_0 has a −2 R δu_prev term
        u_base = self._slices["u"].start
        q[u_base:u_base + self.n_u] = -2.0 * (self.R @ np.array([delta_u_prev])).flatten()

        # --- Update RHS l, u ---
        l_new = self._l.copy()
        u_new = self._u.copy()
        # Dynamics row k=0: RHS = A·δx_0
        rhs0 = self.A @ delta_x0
        l_new[0:self.n_x] = rhs0
        u_new[0:self.n_x] = rhs0
        # Rate constraint at k=0: l = du_min + δu_prev, u = du_max + δu_prev
        l_new[self._rate_row_k0] = self.du_min + delta_u_prev
        u_new[self._rate_row_k0] = self.du_max + delta_u_prev

        self._solver.update(q=q, l=l_new, u=u_new)
        t0 = time.perf_counter()
        result = self._solver.solve()
        wall_ms = (time.perf_counter() - t0) * 1000.0

        status = str(result.info.status).lower()
        block_reason = _block_reason_for(status)

        if block_reason is not None:
            return {
                "status": status,
                "block_reason": block_reason,
                "delta_u": None,
                "u_next": None,
                "iterations": int(result.info.iter),
                "solve_ms": wall_ms,
                "slack_violation_current_a": None,
            }

        z = np.asarray(result.x, dtype=np.float64).flatten()
        delta_u_first = float(z[u_base])               # δu_0
        u_next_absolute = self.u_eq[0] + delta_u_first  # absolute command voltage

        # Slack violation at k=0 (most relevant for the next tick)
        eI_base = self._slices["eI"].start
        slack_I = float(z[eI_base])

        return {
            "status": status,
            "block_reason": None,
            "delta_u": delta_u_first,
            "u_next": u_next_absolute,
            "iterations": int(result.info.iter),
            "solve_ms": wall_ms,
            "slack_violation_current_a": slack_I,
        }


def _block_reason_for(status: str) -> str | None:
    """Map an osqp status string to a block_reason or None if acceptable.

    Returns None for ``solved`` and ``solved inaccurate`` (which we still
    accept but downstream may flag with reduced confidence).
    """
    if status in ("solved",):
        return None
    if status in ("solved inaccurate",):
        return None
    return _BLOCK_REASON_MAP.get(status, "mpc_solver_error")
