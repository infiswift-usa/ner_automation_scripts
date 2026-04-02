"""PV plant component specifications (PCS, modules)."""

from components.pcs import PCSSpec, SG100CX_JP, get_pcs_spec, PCS_REGISTRY
from components.pv_module import (
    PVModuleSpec,
    NER132M625E_NGD,
    get_pv_module_spec,
    PV_MODULE_REGISTRY,
)

__all__ = [
    "PCSSpec",
    "SG100CX_JP",
    "get_pcs_spec",
    "PCS_REGISTRY",
    "PVModuleSpec",
    "NER132M625E_NGD",
    "get_pv_module_spec",
    "PV_MODULE_REGISTRY",
]
