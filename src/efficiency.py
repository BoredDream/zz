"""Shared storage-efficiency convention for Questions 1--4."""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt


@dataclass(frozen=True)
class EfficiencyParameters:
    """One-way efficiencies used by S[t+1] = S[t] + eta_c*C - D/eta_d."""

    eta_charge: float
    eta_discharge: float

    def __post_init__(self) -> None:
        for name, value in (("eta_charge", self.eta_charge), ("eta_discharge", self.eta_discharge)):
            if not 0.0 < value <= 1.0:
                raise ValueError(f"{name} must lie in (0, 1], got {value}")

    @property
    def roundtrip_efficiency(self) -> float:
        return self.eta_charge * self.eta_discharge

    @classmethod
    def symmetric_roundtrip(cls, roundtrip_efficiency: float) -> "EfficiencyParameters":
        if not 0.0 < roundtrip_efficiency <= 1.0:
            raise ValueError("roundtrip_efficiency must lie in (0, 1]")
        eta = sqrt(roundtrip_efficiency)
        return cls(eta, eta)


DEFAULT_EFFICIENCY = EfficiencyParameters(0.90, 0.90)

EFFICIENCY_SCENARIOS = {
    "roundtrip90": EfficiencyParameters.symmetric_roundtrip(0.90),
    "oneway90": DEFAULT_EFFICIENCY,
}
