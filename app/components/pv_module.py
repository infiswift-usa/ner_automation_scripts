"""
PV module specifications for overload rate and simulation calculations.

Source: specs/NER132M625E-NGD.pdf (Next Energy Resources)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PVModuleSpec:
    """Datasheet specs for a PV module model."""

    model: str
    # Electrical (STC: 1000 W/m², 25°C)
    pmax_w: float  # Nominal max power (W)
    vmp: float  # Voltage at max power (V)
    imp: float  # Current at max power (A)
    voc: float  # Open-circuit voltage (V)
    isc: float  # Short-circuit current (A)
    # Limits
    max_system_voltage_v: int  # Max system voltage (V)
    max_overcurrent_protection_a: int  # Max series fuse rating (A)
    # Temperature coefficients (%/°C)
    gamma_pmax: float  # Pmax temp coeff (e.g. -0.290)
    gamma_voc: float  # Voc temp coeff
    gamma_isc: float  # Isc temp coeff
    # Optional
    bifaciality: float | None = None  # Rear/front ratio (e.g. 0.80)
    nmot_c: float | None = None  # Nominal module operating temp (°C)


# --- NER132M625E-NGD (from datasheet) ---

NER132M625E_NGD = PVModuleSpec(
    model="NER132M625E-NGD",
    pmax_w=625.0,
    vmp=41.69,
    imp=14.99,
    voc=49.19,
    isc=16.19,
    max_system_voltage_v=1500,
    max_overcurrent_protection_a=35,
    gamma_pmax=-0.290,  # 最大出力温度係数 (%/°C)
    gamma_voc=-0.250,  # 開放電圧温度係数 (%/°C)
    gamma_isc=0.043,   # 短絡電流温度係数 (%/°C)
    bifaciality=0.80,  # 裏面側出力÷表面側出力 (80±5%)
    nmot_c=41.0,
)

# Registry for lookup by model name (e.g. from plant_specs)
PV_MODULE_REGISTRY: dict[str, PVModuleSpec] = {
    "NER132M625E-NGD": NER132M625E_NGD,
}


def get_pv_module_spec(model: str) -> PVModuleSpec | None:
    """Return PV module spec for model name, or None if unknown."""
    return PV_MODULE_REGISTRY.get(model)
