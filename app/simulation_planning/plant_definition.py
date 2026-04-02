"""
Transform LLM-extracted plant specs into a base plant structure.

Expands grouped PCS configs (with pcs_count) into individual PCS entries
with unique IDs for downstream simulation and Maxifit automation.
"""

from typing import Any


def build_base_plant_structure(specs: dict[str, Any]) -> dict[str, Any]:
    """Expand grouped PCS configs into individual PCS entries with IDs.

    Each entry in pcs_config with pcs_count N becomes N separate entries
    in the output, ordered by group then by index within group.
    Each individual PCS receives a unique pcs_id (integer, starting at 1).

    Args:
        specs: Plant specs from LLM, with keys source, location, pcs_config.
            Each pcs_config entry has pcs_type, strings, modules_per_string,
            module_type, tilt, azimuth, pcs_count (and any other fields).

    Returns:
        Dict with same source/location, but pcs_config is an ordered list
        of individual PCS dicts, each with pcs_id and without pcs_count.
    """
    source = specs.get("source", "")
    location = specs.get("location", {})
    pcs_config = specs.get("pcs_config", [])

    # Build ordered list of individual PCSs
    individual_pcs: list[dict[str, Any]] = []
    pcs_index = 1

    for group in pcs_config:
        pcs_count = group.get("pcs_count", 1)
        # Copy all fields except pcs_count for each individual PCS
        base_pcs = {k: v for k, v in group.items() if k != "pcs_count"}

        for _ in range(pcs_count):
            pcs_entry = base_pcs.copy()
            pcs_entry["pcs_id"] = pcs_index
            individual_pcs.append(pcs_entry)
            pcs_index += 1

    return {
        "source": source,
        "location": location,
        "pcs_config": individual_pcs,
    }
