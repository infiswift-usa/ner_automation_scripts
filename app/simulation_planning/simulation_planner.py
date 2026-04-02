"""
Orchestrate plant specs (JSON) → base plant structure → panel placement permutations.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import sys
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from simulation_planning.panel_placement_permutations import (
    generate_panel_placement_permutations,
    reorder_panel_placement_permutations_for_minimal_cost,
)
from simulation_planning.plant_definition import build_base_plant_structure


class SimulationPlanner:
    """Load plant specs from JSON, expand PCS groups, and generate panel placement permutations."""

    def __init__(self, specs: dict[str, Any]) -> None:
        self._specs = specs
        self._base_plant: dict[str, Any] | None = None

    @classmethod
    def from_json_path(cls, path: Path | str) -> SimulationPlanner:
        """Parse plant specs from a UTF-8 JSON file."""
        p = Path(path)
        with p.open(encoding="utf-8") as f:
            specs: dict[str, Any] = json.load(f)
        return cls(specs)

    @property
    def specs(self) -> dict[str, Any]:
        """Raw plant specs dict (e.g. from LLM extraction)."""
        return self._specs

    @property
    def base_plant(self) -> dict[str, Any]:
        """Expanded plant: individual PCS rows with pcs_id (see build_base_plant_structure)."""
        if self._base_plant is None:
            self._base_plant = build_base_plant_structure(self._specs)
        return self._base_plant

    def panel_placement_permutations(
        self,
        *,
        reorder_for_minimal_cost: bool = True,
        overload_min: float = 100.0,
        overload_max: float = 140.0,
        overload_step: float = 5.0,
        tilt_min: float = 0.0,
        tilt_max: float = 40.0,
        tilt_step: float = 5.0,
    ) -> list[dict[str, Any]]:
        """Generate panel placement permutations from the base plant, optionally TSP-reordered for GUI."""
        permutations = generate_panel_placement_permutations(
            self.base_plant,
            overload_min=overload_min,
            overload_max=overload_max,
            overload_step=overload_step,
            tilt_min=tilt_min,
            tilt_max=tilt_max,
            tilt_step=tilt_step,
        )
        if reorder_for_minimal_cost and permutations:
            return reorder_panel_placement_permutations_for_minimal_cost(permutations)
        return permutations

    def automation_payload(
        self,
        *,
        reorder_for_minimal_cost: bool = True,
        overload_min: float = 100.0,
        overload_max: float = 140.0,
        overload_step: float = 5.0,
        tilt_min: float = 0.0,
        tilt_max: float = 40.0,
        tilt_step: float = 5.0,
    ) -> dict[str, Any]:
        """Bundle specs and ordered permutations for MaxifitRunner or other automation."""
        return {
            "specs": self.specs,
            "ordered_permutations": self.panel_placement_permutations(
                reorder_for_minimal_cost=reorder_for_minimal_cost,
                overload_min=overload_min,
                overload_max=overload_max,
                overload_step=overload_step,
                tilt_min=tilt_min,
                tilt_max=tilt_max,
                tilt_step=tilt_step,
            ),
        }