"""
High-level Python API for GeoMetrics.

Example usage::

    from geometrics import GeoMetrics

    gm = GeoMetrics()
    report = gm.check(
        "locations.csv",
        variables=["Landsat8_NDVI:NDVI"],
        lat_col="lat", lon_col="lon", timestamp_col="date",
    )
    # report["available"] and report["missing"] are lists of dicts

    df = gm.fetch(
        "locations.csv",
        variables=["Landsat8_NDVI:NDVI"],
    )
    # df is a pandas DataFrame with columns:
    # lat, lon, cell_id, source, parameter, timestamp, value, level, aggregated
"""

from __future__ import annotations

from typing import Union

import pandas as pd

from geometrics.backends.hiergp import HierGPBackend
from geometrics.config import GeoMetricsConfig, load_config
from geometrics.store.db import get_engine
from geometrics.store.query import DataQuery, VariableSpec, check_availability, fetch, resolve


class GeoMetrics:
    """
    Main entry point for the GeoMetrics package.

    Loads config from ~/.geometrics/config.json by default.
    Pass a GeoMetricsConfig object to override.
    """

    def __init__(self, config: GeoMetricsConfig | None = None):
        self.config = config or load_config()
        self.engine = get_engine(self.config.db_url)
        self.backend = HierGPBackend()

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def check(
        self,
        locations: Union[str, pd.DataFrame],
        variables: list[str],
        lat_col: str = "latitude",
        lon_col: str = "longitude",
        timestamp_col: str = "timestamp",
    ) -> dict:
        """
        Check which (location, variable, timestamp) combinations have data in the store.

        locations: CSV file path or DataFrame with columns: lat, lon, timestamp.
        variables: list of "Source:parameter" strings, e.g. ["Landsat8_NDVI:NDVI"].

        Returns {"available": [...], "missing": [...]} where each item is a dict
        with keys: lat, lon, cell_id, source, parameter, timestamp, requested_level,
        native_level, variable_id, and (for missing) reason.
        """
        data = self._load(locations)
        rows = self._extract(data, lat_col, lon_col, timestamp_col)
        query = DataQuery(
            rows=rows,
            variables=[VariableSpec.parse(v) for v in variables],
        )
        items = resolve(self.engine, self.backend, query)
        return check_availability(self.engine, self.backend, items)

    def fetch(
        self,
        locations: Union[str, pd.DataFrame],
        variables: list[str],
        lat_col: str = "latitude",
        lon_col: str = "longitude",
        timestamp_col: str = "timestamp",
    ) -> pd.DataFrame:
        """
        Fetch stored observations for the given locations and variables.

        Returns a DataFrame with columns:
          lat, lon, cell_id, source, parameter, timestamp, value, level, aggregated
        """
        data = self._load(locations)
        rows = self._extract(data, lat_col, lon_col, timestamp_col)
        query = DataQuery(
            rows=rows,
            variables=[VariableSpec.parse(v) for v in variables],
        )
        items = resolve(self.engine, self.backend, query)
        return fetch(self.engine, self.backend, items)

    def gee_submit(
        self,
        missing_items: list[dict],
        gdrive_folder: str,
        batch_size: int = 1000,
    ) -> list[int]:
        """
        Submit GEE extraction jobs for items returned by check()["missing"].

        gdrive_folder: root Drive folder. Each source gets a subfolder inside it,
            e.g. gdrive_folder/Landsat_NDVI/batch_001.csv
        batch_size: max features per GEE export task (default 1000).
        Returns a list of local job_ids in submission order.
        """
        from geometrics.extraction.dispatch import dispatch

        if not missing_items:
            print("Nothing to submit.")
            return []

        job_ids = dispatch(
            self.engine, self.config, self.backend, missing_items,
            gdrive_folder=gdrive_folder,
            batch_size=batch_size,
        )
        print(f"\nSubmitted {len(job_ids)} job(s). Track with: gm.jobs()")
        return job_ids

    def jobs(self, status: str | None = None) -> pd.DataFrame:
        """
        List submitted jobs, optionally filtered by status.

        Status values: PENDING, RUNNING, COMPLETED, FAILED, CANCELLED, EXPIRED, INGESTED
        """
        from geometrics.store.jobs import list_jobs
        rows = list_jobs(self.engine, status=status)
        df = pd.DataFrame([r._asdict() for r in rows])
        return df.drop(columns=["ingested_at"], errors="ignore")

    def ingest(self, gdrive_folder: str) -> dict:
        """
        Ingest GEE-exported CSVs from a Drive folder into the database.

        gdrive_folder: the folder name passed to gee_submit (e.g. "extract-20").
            Resolved against gdrive_base from config to find the local path.

        Scans for all *.csv files in the folder, parses variable_name as
        "SourceName:variable", and inserts rows into observations.

        Returns {filename: rows_inserted} for each file processed.
        """
        from pathlib import Path
        from geometrics.store.ingest import ingest_folder

        folder_path = Path(self.config.gdrive_base.strip().replace("\\ ", " ")) / gdrive_folder
        return ingest_folder(self.engine, folder_path)

    def check_status(self) -> dict:
        """
        Poll GEE for all active (PENDING/RUNNING) jobs and update local status.

        Returns a summary dict {status: count}.
        Requires ee.Initialize() to have been called.
        """
        from geometrics.store.jobs import check_status
        return check_status(self.engine)

    def register_sources(self) -> None:
        """Register all catalog sources and their variables in the database."""
        from geometrics.catalog import CATALOG
        from geometrics.extraction.base import ensure_source

        for spec in CATALOG.values():
            ensure_source(
                engine=self.engine,
                name=spec["name"],
                native_level=spec["native_level"],
                pixel_resolution_m=spec["pixel_resolution_m"],
                source_temporal_granularity=spec["source_temporal_granularity"],
                temporal_granularity=spec["temporal_granularity"],
                variable_defs=spec["variables"],
            )
            print(f"  registered: {spec['name']} ({len(spec['variables'])} variable(s))")
        print(f"\n{len(CATALOG)} source(s) registered.")

    def init_db(self) -> None:
        """Create all database tables (safe to call on an existing DB)."""
        from geometrics.store.schema import initialize_db
        initialize_db(self.engine)

    def show_config(self) -> dict:
        """Return the current configuration as a plain dict."""
        import dataclasses
        return dataclasses.asdict(self.config)

    @staticmethod
    def list_sources() -> list[dict]:
        """
        Return catalog metadata for all implemented sources.

        Each dict includes: name, description, gee_collection, pixel_resolution_m,
        native_level, source_temporal_granularity, temporal_granularity, variables.
        """
        from geometrics.catalog import CATALOG
        return list(CATALOG.values())

    @staticmethod
    def list_variables(source: str) -> list[dict]:
        """
        Return variable metadata for a single source.

        Each dict includes: name, unit, description.
        Raises ValueError if the source is not in the catalog.
        """
        from geometrics.catalog import get_source
        return get_source(source)["variables"]

    @staticmethod
    def configure(
        db_url: str | None = None,
        gdrive_base: str | None = None,
        backend: str | None = None,
    ) -> "GeoMetrics":
        """
        Save a new config and return a GeoMetrics instance pointing at it.

        Only the fields you pass are updated; the rest keep their current values.

        Example::

            gm = GeoMetrics.configure(db_url="postgresql://user:pass@localhost/mydb")
        """
        from geometrics.config import DEFAULT_CONFIG_PATH, save_config
        current = load_config()
        def _clean_path(p: str) -> str:
            return p.strip().replace("\\ ", " ")

        updated = GeoMetricsConfig(
            db_url=db_url if db_url is not None else current.db_url,
            gdrive_base=_clean_path(gdrive_base) if gdrive_base is not None else current.gdrive_base,
            backend=backend if backend is not None else current.backend,
        )
        save_config(updated, DEFAULT_CONFIG_PATH)
        import dataclasses
        print(f"Config saved to {DEFAULT_CONFIG_PATH}")
        print(dataclasses.asdict(updated))
        return GeoMetrics(updated)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load(locations: Union[str, pd.DataFrame]) -> pd.DataFrame:
        if isinstance(locations, pd.DataFrame):
            return locations
        return pd.read_csv(locations)

    @staticmethod
    def _extract(
        data: pd.DataFrame,
        lat_col: str,
        lon_col: str,
        timestamp_col: str,
    ) -> list[tuple[float, float, str]]:
        required = [c for c in (lat_col, lon_col, timestamp_col) if c not in data.columns]
        if required:
            raise ValueError(
                f"Required column(s) not found in data: {required}. "
                f"Expected columns: {lat_col!r}, {lon_col!r}, {timestamp_col!r}."
            )
        return list(zip(data[lat_col], data[lon_col], data[timestamp_col].astype(str)))
