"""
PCS (power conditioning system / inverter) specifications.

Source: specs/SG100CX-JP.pdf (Sungrow)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PCSSpec:
    """Datasheet specs for a PCS/inverter model."""

    model: str
    # AC output (denominator for overload rate)
    ac_rated_kw: float  # Rated AC output (kW) @ 50°C
    ac_rated_kva: float  # Rated apparent power (kVA)
    ac_max_kva: float | None  # Max apparent power (kVA), if different
    # Efficiency
    eta_max: float  # Max conversion efficiency (0–1, e.g. 0.987)
    eta_euro: float | None  # European efficiency (0–1)
    # DC input limits
    vdc_max_v: int  # Max input voltage (V)
    vdc_min_v: int  # Min operating voltage (V)
    vdc_rated_v: int  # Rated input voltage (V)
    vdc_mppt_min_v: int  # MPPT voltage range min (V)
    vdc_mppt_max_v: int  # MPPT voltage range max (V)
    mppt_count: int  # Number of MPPT trackers
    strings_per_mppt: int  # Max strings per MPPT
    idc_max_per_mppt_a: float  # Max input current per MPPT (A)
    isc_max_per_mppt_a: float  # Max short-circuit current per MPPT (A)
    # AC output
    vac_rated_v: int  # Rated output voltage (V)
    vac_min_v: int  # Output voltage range min (V)
    vac_max_v: int  # Output voltage range max (V)
    iac_rated_a: float  # Rated output current (A)
    iac_max_a: float  # Max output current (A)
    # Derating
    temp_derate_c: float | None = None  # Temp above which output is limited (°C)


# --- SG100CX-JP (from datasheet) ---

SG100CX_JP = PCSSpec(
    model="SG100CX-JP",
    ac_rated_kw=100.0,  # 100 kW @ 50°C
    ac_rated_kva=100.0,  # 100 kVA (出荷値)
    ac_max_kva=120.0,   # 120 kVA (最大値)
    eta_max=0.987,      # 98.70%
    eta_euro=0.984,     # 98.40%
    vdc_max_v=1100,
    vdc_min_v=200,
    vdc_rated_v=660,
    vdc_mppt_min_v=550,
    vdc_mppt_max_v=850,
    mppt_count=12,
    strings_per_mppt=2,
    idc_max_per_mppt_a=26.0,   # 12 * 26 A
    isc_max_per_mppt_a=40.0,   # 12 * 40 A
    vac_rated_v=440,
    vac_min_v=374,
    vac_max_v=506,
    iac_rated_a=131.2,
    iac_max_a=158.8,
    temp_derate_c=50.0,  # > 50°C 出力制限
)

# Registry for lookup by model name (e.g. from plant_specs)
PCS_REGISTRY: dict[str, PCSSpec] = {
    "SG100CX-JP": SG100CX_JP,
    "SunGrow SG100CX-JP":SG100CX_JP
}


def get_pcs_spec(model: str) -> PCSSpec | None:
    """Return PCS spec for model name, or None if unknown."""
    return PCS_REGISTRY.get(model)
