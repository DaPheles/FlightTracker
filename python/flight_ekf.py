'''
    Extended Kalman Filter for flight position prediction.

    State vector (7-D):
        [lat_deg, lng_deg, hdg_deg, vg_m_s, alt_ft, valt_ft_s, omega_deg_s]

    Motion model: constant speed / climb-rate, turn rate integrated into heading.
    Omega (turn rate, deg/s) decays exponentially toward zero between measurements,
    so a detected turn gradually straightens out if not reinforced by new data —
    the "exponential model" that blends between straight and curved prediction
    proportional to the EKF's own estimate of the current turn rate.

    Measurement model: direct observation of lat, lng, hdg, vg, alt (5 of 7 states).
    Omega is inferred indirectly from consecutive heading measurements via Kalman.
'''

import math
import time
import numpy as np
from constants import (EKF_EARTH_RADIUS_M, EKF_Q, EKF_R, EKF_P0, EKF_OMEGA_TAU,
                       EKF_Q_GROUND, EKF_R_GROUND,
                       EKF_LANDING_ALT_FT, EKF_LANDING_SPD_KTS)

# Unit conversion helpers
_KNOTS_TO_MS = 1.852 / 3.6      # 1 knot → m/s  (1.852 km/h / 3.6)
_D2R = math.pi / 180.0
_R2D = 180.0 / math.pi
_R_M = EKF_EARTH_RADIUS_M


class FlightEKF:
    """
    Extended Kalman Filter that tracks and predicts flight position.

    State: [lat_deg, lng_deg, hdg_deg, vg_m_s, alt_ft, valt_ft_s, omega_deg_s]

    The 7th state, omega (turn rate in deg/s), is what enables curved-path
    prediction during turns.  It is estimated from the sequence of heading
    measurements and decays exponentially during prediction, so the predicted
    path automatically blends between curved (turn ongoing) and straight (no
    new turn evidence) proportional to the magnitude of omega.

    Usage:
        ekf = FlightEKF(lat, lng, hdg, speed_kts, alt_ft)
        ekf.predict(dt)        # forward-propagate by dt seconds
        ekf.update(...)        # apply a new FR24 measurement
        ekf.step(monotonic)    # auto-dt predict + reset timestamp
        lat, lng = ekf.lat, ekf.lng
    """

    def __init__(
        self,
        lat: float,
        lng: float,
        hdg_deg: float,
        speed_kts: float,
        alt_ft: float,
        valt_ft_s: float = 0.0,
    ) -> None:
        vg_m_s = speed_kts * _KNOTS_TO_MS
        # Initial omega = 0 (assume straight flight until measurements say otherwise)
        self._x = np.array([lat, lng, hdg_deg, vg_m_s, alt_ft, valt_ft_s, 0.0], dtype=float)
        self._P = np.diag(EKF_P0)        # 7×7
        self._Q_rate = np.diag(EKF_Q)   # 7×7, scaled by dt inside predict()
        self._R = np.diag(EKF_R)        # 5×5
        # H selects lat, lng, hdg, vg, alt from the 7-D state (omega unobserved)
        self._H = np.zeros((5, 7))
        for i in range(5):
            self._H[i, i] = 1.0
        self._I = np.eye(7)
        self._ts = time.monotonic()

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def lat(self) -> float:
        return float(self._x[0])

    @property
    def lng(self) -> float:
        return float(self._x[1])

    @property
    def heading(self) -> float:
        return float(self._x[2])

    @property
    def speed_kts(self) -> float:
        return float(self._x[3]) / _KNOTS_TO_MS

    @property
    def altitude(self) -> float:
        return float(self._x[4])

    @property
    def omega(self) -> float:
        """Current turn rate estimate in degrees per second."""
        return float(self._x[6])

    # ------------------------------------------------------------------
    # Core EKF steps
    # ------------------------------------------------------------------

    def predict(self, dt: float) -> None:
        """Propagate state and covariance forward by dt seconds.

        Heading advances by omega*dt (curved-path model).
        Omega itself decays exponentially so a detected turn gradually
        straightens out when no new turn evidence arrives.
        """
        if dt <= 0.0:
            return

        lat, lng, hdg, vg, alt, valt, omega = self._x
        h = hdg * _D2R
        phi = lat * _D2R

        cos_h = math.cos(h)
        sin_h = math.sin(h)
        cos_phi = math.cos(phi)
        sin_phi = math.sin(phi)
        cos_phi_safe = cos_phi if abs(cos_phi) > 1e-9 else 1e-9

        # State transition — heading now changes by omega*dt
        lat_new   = lat  + (vg * dt / _R_M) * cos_h * _R2D
        lng_new   = lng  + (vg * dt / _R_M) * sin_h / cos_phi_safe * _R2D
        hdg_new   = (hdg + omega * dt) % 360.0   # ← curved path
        vg_new    = vg
        alt_new   = alt  + valt * dt
        valt_new  = valt
        # Exponential decay: assumed turn rate shrinks toward 0 without new evidence
        omega_new = omega * math.exp(-dt / EKF_OMEGA_TAU)

        self._x = np.array([lat_new, lng_new, hdg_new, vg_new, alt_new, valt_new, omega_new])

        # Jacobian F (7×7)
        F = self._I.copy()
        tan_phi = sin_phi / cos_phi_safe

        F[0, 2] = -(vg * dt / _R_M) * sin_h                                # dlat/dhdg
        F[0, 3] =  (dt / _R_M) * cos_h * _R2D                              # dlat/dvg
        F[1, 0] =  (vg * dt / _R_M) * sin_h * tan_phi / cos_phi_safe * _D2R * _R2D  # dlng/dlat
        F[1, 2] =  (vg * dt / _R_M) * cos_h / cos_phi_safe                 # dlng/dhdg
        F[1, 3] =  (dt / _R_M) * sin_h / cos_phi_safe * _R2D               # dlng/dvg
        F[2, 6] =  dt                                                        # dhdg/domega  ← new
        F[4, 5] =  dt                                                        # dalt/dvalt
        F[6, 6] =  math.exp(-dt / EKF_OMEGA_TAU)                            # domega/domega ← new

        # Covariance propagation
        Q = self._Q_rate * dt
        self._P = F @ self._P @ F.T + Q

    def update(
        self,
        lat: float,
        lng: float,
        hdg_deg: float,
        speed_kts: float,
        alt_ft: float,
        valt_ft_s: float = 0.0,
    ) -> None:
        """Apply a measurement update from the FR24 API.

        Omega is not directly measured but will be inferred over multiple
        updates from the sequence of hdg observations via the Kalman gain.
        """
        vg_m_s = speed_kts * _KNOTS_TO_MS
        z = np.array([lat, lng, hdg_deg, vg_m_s, alt_ft])

        # Innovation
        y = z - self._H @ self._x
        # Heading wrap-around correction
        y[2] = (y[2] + 180.0) % 360.0 - 180.0

        S = self._H @ self._P @ self._H.T + self._R
        K = self._P @ self._H.T @ np.linalg.inv(S)

        self._x = self._x + K @ y
        # Normalise heading into [0, 360)
        self._x[2] = self._x[2] % 360.0

        # Joseph-form update for numerical stability
        ImKH = self._I - K @ self._H
        self._P = ImKH @ self._P @ ImKH.T + K @ self._R @ K.T

        # Absorb valt from measurement via simple low-pass (not in H)
        alpha = 0.3
        self._x[5] = (1.0 - alpha) * self._x[5] + alpha * valt_ft_s

    def step(self, now: float) -> None:
        """
        Compute dt from the stored timestamp, call predict(), reset timestamp.

        Args:
            now: Current time from time.monotonic()
        """
        dt = now - self._ts
        self._ts = now
        self.predict(dt)

    def adjust_noise(self, spd_kts: float, alt_ft: float) -> None:
        """Blend Q and R between cruise and ground/landing parameters.

        As altitude drops below EKF_LANDING_ALT_FT or speed drops below
        EKF_LANDING_SPD_KTS the EKF transitions toward ground-mode noise:
          - Q heading/speed/omega increase → tracks rapid deceleration and turns
          - R position decreases → trusts measurements more at low speed

        phase=0: cruise  phase=1: fully on ground
        """
        phase_alt = max(0.0, min(1.0, 1.0 - alt_ft  / EKF_LANDING_ALT_FT))
        phase_spd = max(0.0, min(1.0, 1.0 - spd_kts / EKF_LANDING_SPD_KTS))
        phase = max(phase_alt, phase_spd)

        if phase == 0.0:
            return   # cruise: matrices already at default; skip work

        # Blend indices that matter for landing dynamics: hdg(2), vg(3), omega(6)
        for i in (2, 3, 6):
            self._Q_rate[i, i] = EKF_Q[i] + phase * (EKF_Q_GROUND[i] - EKF_Q[i])

        # Blend position measurement noise: lat(0), lng(1)
        for i in (0, 1):
            self._R[i, i] = EKF_R[i] + phase * (EKF_R_GROUND[i] - EKF_R[i])

    def step_ts(self, now: float) -> None:
        """Advance the internal timestamp without predicting.

        Call this while animation is paused so that the next real step()
        computes a small dt instead of the full freeze duration.
        """
        self._ts = now

    def snap_position(self, lat: float, lng: float) -> None:
        """Hard-sync position states to exact coordinates (kept for reference)."""
        self._x[0] = lat
        self._x[1] = lng
