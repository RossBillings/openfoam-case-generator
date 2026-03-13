from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple


@dataclass
class PhysicsConfig:
    """
    Physics parameters for incompressible external aerodynamics.

    velocity:              Freestream velocity vector (m/s). AoA encoded here.
    nu:                    Kinematic viscosity (m²/s). Air at 20°C = 1.5e-5.
    turbulence_model:      OF13 momentumTransport model name.
    turbulence_intensity:  Freestream Tu (fraction). 0.001 = clean tunnel.
    turbulent_length_scale: Integral length scale (m). ~1% of ref length.
    steady_state:          True = SIMPLE, False = PIMPLE transient.
    end_time:              Simulation end time (iterations for steady, s for transient).
    write_interval:        Write output every N steps/seconds.
    """

    velocity: Tuple[float, float, float] = (30.0, 0.0, 0.0)
    nu: float = 1.5e-5
    turbulence_model: str = "kOmegaSST"
    turbulence_intensity: float = 0.001
    turbulent_length_scale: float = 0.05
    steady_state: bool = True
    end_time: float = 1000.0
    write_interval: float = 100.0

    @property
    def U_mag(self) -> float:
        return math.sqrt(sum(v**2 for v in self.velocity))

    @property
    def k_inlet(self) -> float:
        """Turbulent kinetic energy from intensity: k = 1.5*(U*Tu)^2"""
        return 1.5 * (self.U_mag * self.turbulence_intensity) ** 2

    @property
    def omega_inlet(self) -> float:
        """Specific dissipation: omega = sqrt(k) / (Cmu^0.25 * L)"""
        Cmu = 0.09
        return math.sqrt(self.k_inlet) / (Cmu**0.25 * self.turbulent_length_scale)

    @property
    def nut_inlet(self) -> float:
        """Turbulent viscosity: nut = k / omega"""
        return self.k_inlet / max(self.omega_inlet, 1e-10)
