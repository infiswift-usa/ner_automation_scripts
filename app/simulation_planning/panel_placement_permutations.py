"""
Generate panel placement permutations for simulation.

Creates all combinations of overload rate and tilt angle, with strings
distributed evenly across PCSs (lower IDs get +1 when uneven).
Reorders permutations to minimize GUI automation cost (TSP).
"""

from typing import Any

from components import get_pcs_spec, get_pv_module_spec

# Cost model for GUI automation (calibrated from run log: tilt change ~57s, string-only ~30s)
COST_OPEN_PCS_CONFIG = 15  # units to open a PCS config window
COST_CHANGE_VALUE = 2  # units per numeric value changed (strings or tilt)
# Flat penalty for any tilt change (favors tilt-first ordering)
COST_TILT_CHANGE = 80
# Penalty per non-sequential tilt step (e.g. 0→10 instead of 0→5→10)
PENALTY_TILT_JUMP = 500


def _distribute_strings(total_strings: int, num_pcs: int) -> list[int]:
    """Distribute total strings across PCSs; lower indices get +1 when uneven.

    Example: 63 strings, 6 PCSs -> [11, 11, 11, 10, 10, 10]
    """
    base = total_strings // num_pcs
    remainder = total_strings % num_pcs
    # First `remainder` PCSs (lower IDs) get base+1
    return [base + 1] * remainder + [base] * (num_pcs - remainder)


def generate_panel_placement_permutations(
    base_plant: dict[str, Any],
    *,
    overload_min: float = 100.0,
    overload_max: float = 140.0,
    overload_step: float = 5.0,
    tilt_min: float = 0.0,
    tilt_max: float = 40.0,
    tilt_step: float = 5.0,
) -> list[dict[str, Any]]:
    """Generate all panel placement permutations for overload rate and tilt.

    Varies only the number of strings per PCS (distributed evenly, lower IDs
    get +1 when uneven) and tilt angle. Modules per string and azimuth are
    preserved from the base plant.

    Args:
        base_plant: Output of build_base_plant_structure (individual PCSs).
        overload_min: Min overload rate (%).
        overload_max: Max overload rate (%).
        overload_step: Step between overload rates (%).
        tilt_min: Min tilt angle (degrees).
        tilt_max: Max tilt angle (degrees).
        tilt_step: Step between tilt angles (degrees).

    Returns:
        List of plant config dicts (one per panel placement permutation), each
        with source, location, pcs_config, and metadata (overload_rate_pct, tilt).
    """
    pcs_config = base_plant.get("pcs_config", [])
    if not pcs_config:
        return []

    num_pcs = len(pcs_config)
    # Use first PCS for module/PCS specs (assume uniform plant)
    first = pcs_config[0]
    pcs_type = first.get("pcs_type", "")
    module_type = first.get("module_type", "")
    modules_per_string = first.get("modules_per_string", 16)

    pcs_spec = get_pcs_spec(pcs_type)
    module_spec = get_pv_module_spec(module_type)
    if pcs_spec is None or module_spec is None:
        raise ValueError(
            f"Unknown pcs_type={pcs_type!r} or module_type={module_type!r}; "
            "register specs in app.components"
        )

    total_ac_kw = 0.0
    for p in pcs_config:
        spec = get_pcs_spec(p.get("pcs_type", ""))
        if spec is None:
            raise ValueError(f"Unknown pcs_type {p.get('pcs_type')!r}")
        total_ac_kw += spec.ac_rated_kw
    if total_ac_kw <= 0:
        raise ValueError("Total AC capacity must be positive")

    # DC per string (kW)
    dc_per_string_kw = modules_per_string * module_spec.pmax_w / 1000.0

    overload_rates = []
    r = overload_min
    while r <= overload_max:
        overload_rates.append(r)
        r += overload_step

    tilt_angles = []
    t = tilt_min
    while t <= tilt_max:
        tilt_angles.append(t)
        t += tilt_step

    result: list[dict[str, Any]] = []

    for overload_pct in overload_rates:
        total_dc_kw = total_ac_kw * (overload_pct / 100.0)
        total_strings = round(total_dc_kw / dc_per_string_kw)
        total_strings = max(total_strings, num_pcs)  # At least 1 string per PCS

        strings_per_pcs = _distribute_strings(total_strings, num_pcs)

        for tilt in tilt_angles:
            new_pcs_config = []
            for i, pcs in enumerate(pcs_config):
                new_pcs = {k: v for k, v in pcs.items()}
                new_pcs["strings"] = strings_per_pcs[i]
                new_pcs["tilt"] = tilt
                new_pcs_config.append(new_pcs)

            config = {
                "source": base_plant.get("source", ""),
                "location": base_plant.get("location", {}),
                "pcs_config": new_pcs_config,
                "overload_rate_pct": overload_pct,
                "tilt": tilt,
            }
            result.append(config)

    return result


def _transition_cost(
    config_a: dict[str, Any],
    config_b: dict[str, Any],
    num_pcs: int,
    tilt_step: float = 5.0,
) -> int:
    """Cost (units) to transition between two panel placement permutations via GUI.

    - Opening a PCS config window: COST_OPEN_PCS_CONFIG units
    - Changing a value (strings or tilt): COST_CHANGE_VALUE units
    - Tilt change adds COST_TILT_CHANGE flat penalty (favors tilt-first ordering)
    - Non-sequential tilt changes (e.g. 0→10 instead of 0→5→10) add PENALTY_TILT_JUMP
    """
    tilt_changed = config_a["tilt"] != config_b["tilt"]
    strings_a = [p["strings"] for p in config_a["pcs_config"]]
    strings_b = [p["strings"] for p in config_b["pcs_config"]]
    num_string_changes = sum(1 for i in range(num_pcs) if strings_a[i] != strings_b[i])

    if tilt_changed:
        # Must visit all PCSs; flat tilt penalty favors minimizing tilt transitions
        base = (
            COST_TILT_CHANGE
            + num_pcs * (COST_OPEN_PCS_CONFIG + COST_CHANGE_VALUE)
            + num_string_changes * COST_CHANGE_VALUE
        )
        tilt_jump = abs(config_b["tilt"] - config_a["tilt"]) / tilt_step
        penalty = int(max(0, tilt_jump - 1) * PENALTY_TILT_JUMP)
        return base + penalty
    else:
        # Only visit PCSs where strings changed
        return num_string_changes * (COST_OPEN_PCS_CONFIG + COST_CHANGE_VALUE)


def reorder_panel_placement_permutations_for_minimal_cost(
    permutations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Reorder panel placement permutations to minimize total transition cost for GUI automation.

    Starts at the permutation with least overload rate and smallest tilt angle.
    Uses TSP (OR-Tools) to find a near-optimal visitation order.

    Args:
        permutations: List of plant config dicts from generate_panel_placement_permutations.

    Returns:
        Reordered list, first element = (min overload, min tilt).
    """
    if len(permutations) <= 1:
        return list(permutations)

    num_pcs = len(permutations[0]["pcs_config"])
    tilts = sorted(set(c["tilt"] for c in permutations))
    tilt_step = tilts[1] - tilts[0] if len(tilts) > 1 else 5.0

    # Find start index: permutation with min overload, then min tilt
    start_idx = min(
        range(len(permutations)),
        key=lambda i: (permutations[i]["overload_rate_pct"], permutations[i]["tilt"]),
    )

    # Build cost matrix (integer for OR-Tools)
    n = len(permutations)
    cost_matrix = [
        [
            _transition_cost(permutations[i], permutations[j], num_pcs, tilt_step)
            for j in range(n)
        ]
        for i in range(n)
    ]

    try:
        from ortools.constraint_solver import pywrapcp

        manager = pywrapcp.RoutingIndexManager(n, 1, start_idx)
        routing = pywrapcp.RoutingModel(manager)

        def cost_callback(from_idx: int, to_idx: int) -> int:
            from_node = manager.IndexToNode(from_idx)
            to_node = manager.IndexToNode(to_idx)
            return int(cost_matrix[from_node][to_node])

        transit_callback_idx = routing.RegisterTransitCallback(cost_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_idx)

        search_params = pywrapcp.DefaultRoutingSearchParameters()
        search_params.time_limit.seconds = 30

        solution = routing.SolveWithParameters(search_params)
        if solution is None:
            raise RuntimeError("OR-Tools TSP failed to find a solution")

        # Extract route
        index = routing.Start(0)
        route_indices: list[int] = []
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            route_indices.append(node)
            index = solution.Value(routing.NextVar(index))

        return [permutations[i] for i in route_indices]

    except ImportError:
        # Fallback: greedy nearest-neighbor when ortools not installed
        return _reorder_greedy(permutations, start_idx, cost_matrix)


def _reorder_greedy(
    permutations: list[dict[str, Any]],
    start_idx: int,
    cost_matrix: list[list[int | float]],
) -> list[dict[str, Any]]:
    """Greedy nearest-neighbor ordering when OR-Tools unavailable."""
    n = len(permutations)
    unvisited = set(range(n)) - {start_idx}
    order = [start_idx]
    current = start_idx

    while unvisited:
        next_idx = min(unvisited, key=lambda j: cost_matrix[current][j])
        order.append(next_idx)
        unvisited.remove(next_idx)
        current = next_idx

    return [permutations[i] for i in order]