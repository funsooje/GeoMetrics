"""
Query layer: resolve locations to cell_ids, check availability, fetch observations.

Typical workflow:
  query   = DataQuery(locations=[...], variables=[...], timestamps=[...])
  items   = resolve(engine, backend, query)          # lat/lon → cell_id
  report  = check_availability(engine, backend, items)
  # submit GEE jobs for report["missing"] if needed, then ingest
  data_df = fetch(engine, backend, items)            # returns a DataFrame
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sqlalchemy import select
from sqlalchemy.engine import Engine

from geometrics.backends.base import GridBackend
from geometrics.store.schema import observations, sources
from geometrics.store.schema import variables as variables_table


# ---------------------------------------------------------------------------
# Public data classes
# ---------------------------------------------------------------------------

@dataclass
class VariableSpec:
    source: str       # matches sources.name, e.g. "Landsat8_NDVI"
    parameter: str    # matches variables.name, e.g. "NDVI"
    level: int | None = None  # None → use source's native_level

    @classmethod
    def parse(cls, spec: str, level: int | None = None) -> "VariableSpec":
        """Parse 'Source:parameter' shorthand, e.g. 'Landsat8_NDVI:NDVI'."""
        parts = spec.split(":")
        if len(parts) != 2:
            raise ValueError(f"VariableSpec must be 'source:parameter', got: {spec!r}")
        return cls(source=parts[0].strip(), parameter=parts[1].strip(), level=level)

    def __str__(self) -> str:
        return f"{self.source}:{self.parameter}"


@dataclass
class DataQuery:
    rows: list[tuple[float, float, str]]  # [(lat, lon, timestamp), ...]
    variables: list[VariableSpec]


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def resolve(engine: Engine, backend: GridBackend, query: DataQuery) -> list[dict]:
    """
    Resolve each (lat, lon) × variable × timestamp to a cell_id.

    Level per variable: VariableSpec.level if set, else source's native_level.
    Timestamps are snapped to each variable's temporal_granularity before lookup.
    Returns a flat list of dicts — one per (location, variable, timestamp).
    """
    source_meta = _load_source_meta(engine, [v.source for v in query.variables])

    items = []
    for lat, lon, timestamp in query.rows:
        for var_spec in query.variables:
            meta = source_meta[var_spec.source]
            level = var_spec.level if var_spec.level is not None else meta["native_level"]
            cell_id = backend.point_to_cell(lat, lon, level)
            snapped = _snap_timestamp(timestamp, meta["temporal_granularity"])
            items.append({
                "lat": lat,
                "lon": lon,
                "cell_id": cell_id,
                "source": var_spec.source,
                "parameter": var_spec.parameter,
                "original_timestamp": timestamp,
                "timestamp": snapped,
                "temporal_granularity": meta["temporal_granularity"],
                "requested_level": level,
                "native_level": meta["native_level"],
                "variable_id": meta["variable_ids"].get(var_spec.parameter),
            })
    return items


def check_availability(engine: Engine, backend: GridBackend, resolved_items: list[dict]) -> dict:
    """
    Check which resolved items already have data in the store.

    Coarser-than-native requests: checks whether any descendant cells have data.
    Returns {"available": [...], "missing": [...]} where missing items include a "reason" key.
    """
    available, missing = [], []

    for item in resolved_items:
        if item["variable_id"] is None:
            missing.append({**item, "reason": "unknown variable"})
            continue

        requested_level = item["requested_level"]
        native_level = item["native_level"]

        if requested_level > native_level:
            missing.append({**item, "reason": "requested level finer than native"})
            continue

        cell_ids_to_check = (
            [item["cell_id"]]
            if requested_level == native_level
            else _get_descendants(backend, item["cell_id"], native_level)
        )

        if _has_data(engine, cell_ids_to_check, item["variable_id"], item["timestamp"]):
            available.append(item)
        else:
            missing.append({**item, "reason": "not in store"})

    return {"available": available, "missing": missing}


def fetch(engine: Engine, backend: GridBackend, resolved_items: list[dict]) -> pd.DataFrame:
    """
    Fetch observations for pre-resolved items.

    - Same level as native  → direct lookup.
    - Coarser than native   → averages all stored descendant values.
    - Finer than native     → NaN (cannot synthesise finer data than stored).

    Returns a DataFrame with columns:
      lat, lon, cell_id, source, parameter, timestamp, value, level, aggregated
    """
    rows = []
    for item in resolved_items:
        if item["variable_id"] is None:
            rows.append(_make_row(item, value=None, aggregated=False))
            continue

        requested_level = item["requested_level"]
        native_level = item["native_level"]

        if requested_level > native_level:
            rows.append(_make_row(item, value=None, aggregated=False))
        elif requested_level == native_level:
            value = _lookup_single(engine, item["cell_id"], item["variable_id"], item["timestamp"])
            rows.append(_make_row(item, value=value, aggregated=False))
        else:
            descendants = _get_descendants(backend, item["cell_id"], native_level)
            values = _lookup_many(engine, descendants, item["variable_id"], item["timestamp"])
            value = sum(values) / len(values) if values else None
            rows.append(_make_row(item, value=value, aggregated=True))

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_source_meta(engine: Engine, source_names: list[str]) -> dict[str, dict]:
    unique_names = list(dict.fromkeys(source_names))
    with engine.connect() as conn:
        src_rows = conn.execute(
            select(sources).where(sources.c.name.in_(unique_names))
        ).fetchall()

        unknown = set(unique_names) - {r.name for r in src_rows}
        if unknown:
            raise ValueError(f"Unknown source(s): {unknown}. Register them before querying.")

        source_ids = {r.name: r.source_id for r in src_rows}
        native_levels = {r.name: r.native_level for r in src_rows}
        temporal_granularities = {r.name: r.temporal_granularity for r in src_rows}

        var_rows = conn.execute(
            select(variables_table).where(
                variables_table.c.source_id.in_(source_ids.values())
            )
        ).fetchall()

    source_id_to_name = {sid: name for name, sid in source_ids.items()}
    var_by_source: dict[str, dict[str, int]] = {name: {} for name in unique_names}
    for var in var_rows:
        src_name = source_id_to_name[var.source_id]
        var_by_source[src_name][var.name] = var.variable_id

    return {
        name: {
            "native_level": native_levels[name],
            "temporal_granularity": temporal_granularities[name],
            "variable_ids": var_by_source[name],
        }
        for name in unique_names
    }


def _snap_timestamp(timestamp: str, granularity: str) -> str:
    """Truncate a timestamp string to the variable's storage granularity."""
    # timestamps are ISO strings: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS
    date_part = timestamp[:10]  # YYYY-MM-DD
    year, month, _ = date_part.split("-")
    if granularity == "year":
        return f"{year}-01-01"
    if granularity == "month":
        return f"{year}-{month}-01"
    # day, hour, or finer → return date portion as-is
    return date_part


def _get_descendants(backend: GridBackend, cell_id: str, target_level: int) -> list[str]:
    current = backend.cell_level(cell_id)
    if current == target_level:
        return [cell_id]
    if current > target_level:
        return []
    result = []
    for child in backend.cell_children(cell_id):
        result.extend(_get_descendants(backend, child, target_level))
    return result


def _has_data(engine: Engine, cell_ids: list[str], variable_id: int, timestamp: str) -> bool:
    with engine.connect() as conn:
        row = conn.execute(
            select(observations.c.cell_id).where(
                observations.c.cell_id.in_(cell_ids),
                observations.c.variable_id == variable_id,
                observations.c.timestamp == timestamp,
            ).limit(1)
        ).fetchone()
    return row is not None


def _lookup_single(engine: Engine, cell_id: str, variable_id: int, timestamp: str) -> float | None:
    with engine.connect() as conn:
        row = conn.execute(
            select(observations.c.value).where(
                observations.c.cell_id == cell_id,
                observations.c.variable_id == variable_id,
                observations.c.timestamp == timestamp,
            )
        ).fetchone()
    return row.value if row else None


def _lookup_many(
    engine: Engine, cell_ids: list[str], variable_id: int, timestamp: str
) -> list[float]:
    with engine.connect() as conn:
        rows = conn.execute(
            select(observations.c.value).where(
                observations.c.cell_id.in_(cell_ids),
                observations.c.variable_id == variable_id,
                observations.c.timestamp == timestamp,
                observations.c.value.is_not(None),
            )
        ).fetchall()
    return [r.value for r in rows]


def _make_row(item: dict, value: float | None, aggregated: bool) -> dict:
    return {
        "lat": item["lat"],
        "lon": item["lon"],
        "timestamp": item["original_timestamp"],
        "resolved_timestamp": item["timestamp"],
        "source": item["source"],
        "parameter": item["parameter"],
        "value": value,
        "cell_id": item["cell_id"],
        "level": item["requested_level"],
        "aggregated": aggregated,
    }
