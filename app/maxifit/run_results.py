"""
Load Maxifit CSV exports from a simulation run folder into a pandas DataFrame.

Output columns align with ``dbo.pv_generation_results`` (see ``db/sqlserver/001_initial_schema.sql``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pandas as pd

# Matches dbo.pv_generation_results generation columns (excluding FK ids handled separately).
PV_KWH_MONTH_COLUMNS = [f"pv_kwh_month_{i:02d}" for i in range(1, 13)]
YEARLY_TOTAL_COLUMN = "yearly_total_kwh"

# Line prefix for the total-chart CSV row that lists monthly and annual kWh (Japanese Maxifit export).
_ANNUAL_GEN_PREFIX = "年間発電量"


def _parse_monthly_and_yearly_kwh(csv_path: Path) -> tuple[list[float], float]:
    """Extract 12 monthly kWh values and yearly total kWh from a Maxifit export CSV."""
    text = csv_path.read_text(encoding="utf-8")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith(_ANNUAL_GEN_PREFIX):
            continue
        parts = line.split(",")
        # Label + 12 months + yearly total
        if len(parts) < 14:
            raise ValueError(
                f"Expected at least 14 comma-separated fields on 年間発電量 line in {csv_path}, "
                f"got {len(parts)}"
            )
        try:
            monthly = [float(p.strip()) for p in parts[1:13]]
            yearly_total = float(parts[13].strip())
        except ValueError as e:
            raise ValueError(f"Non-numeric value in 年間発電量 row in {csv_path}") from e
        return monthly, yearly_total

    raise ValueError(f"No '{_ANNUAL_GEN_PREFIX}' row found in {csv_path}")


def _normalize_simulation_id(simulation_id: UUID | str | None) -> str | None:
    if simulation_id is None:
        return None
    if isinstance(simulation_id, UUID):
        return str(simulation_id)
    return str(simulation_id)


def maxifit_run_to_dataframe(
    run_dir: Path | str,
    *,
    simulation_id: UUID | str | None = None,
    include_permutation_params: bool = True,
) -> pd.DataFrame:
    """Build one row per permutation from ``run.json``, ``permutations.json``, and ``perm_*.csv`` files.

    Columns match ``dbo.pv_generation_results`` (``permutation_id``, ``simulation_id``,
    ``pv_kwh_month_01`` … ``pv_kwh_month_12``, ``yearly_total_kwh``), plus ``run_id`` for traceability.
    When ``include_permutation_params`` is True, ``overload_rate_pct`` and ``tilt`` are appended
    from each permutation record in ``permutations.json``.

    Args:
        run_dir: Folder containing ``run.json``, ``permutations.json``, and ``perm_NNN.csv`` exports.
        simulation_id: Optional UUID to store in ``simulation_id`` (same for every row). Use when
            aligning with ``dbo.simulations`` / ``dbo.permutations`` in SQL Server.
        include_permutation_params: If True, add overload/tilt from JSON metadata.

    Returns:
        A single DataFrame with one row per permutation in execution order (JSON ``id`` order).
    """
    root = Path(run_dir)
    run_json_path = root / "run.json"
    permutations_json_path = root / "permutations.json"

    if not run_json_path.is_file():
        raise FileNotFoundError(f"Missing run.json: {run_json_path}")
    if not permutations_json_path.is_file():
        raise FileNotFoundError(f"Missing permutations.json: {permutations_json_path}")

    with run_json_path.open(encoding="utf-8") as f:
        run_meta: dict[str, Any] = json.load(f)
    run_id = str(run_meta.get("run_id", root.name))

    with permutations_json_path.open(encoding="utf-8") as f:
        permutations_doc: dict[str, Any] = json.load(f)
    permutations = permutations_doc.get("permutations", [])
    if not permutations:
        return pd.DataFrame()

    sim_id = _normalize_simulation_id(simulation_id)

    rows: list[dict[str, Any]] = []
    for perm in permutations:
        perm_id = perm.get("id")
        if perm_id is None:
            raise ValueError("permutation entry missing 'id' in permutations.json")

        csv_name = f"perm_{int(perm_id):03d}.csv"
        csv_path = root / csv_name
        if not csv_path.is_file():
            raise FileNotFoundError(f"Missing export for permutation {perm_id}: {csv_path}")

        monthly, yearly_total = _parse_monthly_and_yearly_kwh(csv_path)

        row: dict[str, Any] = {
            "run_id": run_id,
            "permutation_id": int(perm_id),
            "simulation_id": sim_id,
        }
        for i, col in enumerate(PV_KWH_MONTH_COLUMNS, start=1):
            row[col] = monthly[i - 1]
        row[YEARLY_TOTAL_COLUMN] = yearly_total

        if include_permutation_params:
            row["overload_rate_pct"] = perm.get("overload_rate_pct")
            row["tilt"] = perm.get("tilt")

        rows.append(row)

    df = pd.DataFrame(rows)
    # Stable column order: metadata, months, yearly, optional params
    base_cols = ["run_id", "permutation_id", "simulation_id", *PV_KWH_MONTH_COLUMNS, YEARLY_TOTAL_COLUMN]
    if include_permutation_params:
        base_cols.extend(["overload_rate_pct", "tilt"])
    df = df.reindex(columns=base_cols)
    return df


def maxifit_perm_csv_to_generation_row(csv_path: Path | str) -> dict[str, Any]:
    """Parse a single ``perm_NNN.csv`` into a dict with ``pv_kwh_month_*`` and ``yearly_total_kwh`` only.

    Useful for unit tests or single-file ingestion without a full run folder.
    """
    path = Path(csv_path)
    monthly, yearly_total = _parse_monthly_and_yearly_kwh(path)
    row: dict[str, Any] = {}
    for i, col in enumerate(PV_KWH_MONTH_COLUMNS, start=1):
        row[col] = monthly[i - 1]
    row[YEARLY_TOTAL_COLUMN] = yearly_total
    return row
