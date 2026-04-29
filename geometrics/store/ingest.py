"""
Ingest GEE-exported CSVs into the observations table.

Expected CSV columns (produced by extraction modules):
  cell_id        - backend cell ID string
  variable_name  - "SourceName:variable" e.g. "Landsat_NDVI:NDVI"
  timestamp      - ISO date/datetime string
  value          - float

GEE also adds 'system:index' and '.geo' columns; these are silently dropped.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.engine import Engine

from geometrics.store.schema import observations, sources, variables

_GEE_META_COLS = {"system:index", ".geo"}
_REQUIRED_COLS = {"cell_id", "variable_name", "timestamp", "value"}


def ingest_folder(engine: Engine, folder_path: str | Path) -> dict:
    """
    Ingest all GEE-exported CSVs found in folder_path into observations.

    Scans for *.csv files, reads each one, resolves variable_id from the
    "SourceName:variable" format in the variable_name column, and inserts
    rows. Duplicates are silently skipped.

    Returns {filename: rows_inserted} for every file processed.
    """
    folder = Path(folder_path)
    if not folder.exists():
        raise FileNotFoundError(f"Folder not found: {folder}")

    csv_files = sorted(folder.glob("*.csv"))
    if not csv_files:
        print(f"No CSV files found in {folder}")
        return {}

    results: dict[str, int] = {}
    for path in csv_files:
        print(f"Ingesting {path.name} …")
        data = _read_csv(path)
        var_map = _build_variable_map(engine, data["variable_name"].unique().tolist())
        data["variable_id"] = data["variable_name"].map(var_map)

        rows = [
            {
                "cell_id": row.cell_id,
                "variable_id": int(row.variable_id),
                "timestamp": row.timestamp,
                "value": row.value if pd.notna(row.value) else None,
            }
            for row in data.itertuples(index=False)
        ]

        inserted = _insert_ignore(engine, rows)
        skipped = len(rows) - inserted
        print(f"  {path.name}: inserted {inserted} row(s), skipped {skipped} duplicate(s).")
        results[path.name] = inserted

    return results


def _read_csv(path: Path) -> pd.DataFrame:
    data: pd.DataFrame = pd.read_csv(path)
    data = data.drop(columns=[c for c in _GEE_META_COLS if c in data.columns])
    missing = _REQUIRED_COLS - set(data.columns)
    if missing:
        raise ValueError(f"{path.name}: missing required columns: {missing}")
    return data[list(_REQUIRED_COLS)]


def _build_variable_map(engine: Engine, qualified_names: list[str]) -> dict[str, int]:
    """
    Resolve "SourceName:variable" strings to variable_id.

    Raises ValueError for any name that doesn't match a known source+variable pair.
    """
    parsed: dict[str, tuple[str, str]] = {}
    for qname in qualified_names:
        if ":" not in qname:
            raise ValueError(
                f"variable_name {qname!r} must be in 'SourceName:variable' format."
            )
        source_name, var_name = qname.split(":", 1)
        parsed[qname] = (source_name, var_name)

    with engine.connect() as conn:
        rows = conn.execute(
            select(
                sources.c.name.label("source_name"),
                variables.c.name.label("var_name"),
                variables.c.variable_id,
            ).join(variables, sources.c.source_id == variables.c.source_id)
        ).fetchall()

    lookup = {(r.source_name, r.var_name): r.variable_id for r in rows}

    result: dict[str, int] = {}
    unknown = []
    for qname, (src, var) in parsed.items():
        vid = lookup.get((src, var))
        if vid is None:
            unknown.append(qname)
        else:
            result[qname] = vid

    if unknown:
        raise ValueError(
            f"Unknown source:variable pair(s): {unknown}. "
            "Run gm.register_sources() if the source has not been registered."
        )
    return result


def _insert_ignore(engine: Engine, rows: list[dict]) -> int:
    if not rows:
        return 0
    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert
            stmt = insert(observations).prefix_with("OR IGNORE")
        elif dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
            stmt = insert(observations).on_conflict_do_nothing(
                index_elements=["cell_id", "variable_id", "timestamp"]
            )
        else:
            from sqlalchemy import insert
            stmt = insert(observations)
        result = conn.execute(stmt, rows)
        return result.rowcount
