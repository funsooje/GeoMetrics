"""
MODIS MOD44B annual percent tree cover extraction.

Each submitted feature carries start_date and end_date as properties.
GEE reads those per-feature at runtime, so different cells can cover
different years within one batch.

Output CSV columns: cell_id, variable_name, timestamp, value
"""

from __future__ import annotations

from geometrics.backends.base import GridBackend
from geometrics.config import GeoMetricsConfig
from geometrics.extraction.base import ensure_source, items_to_ee_feature_collection, submit_export
from geometrics.store.jobs import record_submitted
from sqlalchemy.engine import Engine

_SOURCE_NAME = "MODIS_Treecover"
_NATIVE_LEVEL = 11
_PIXEL_RESOLUTION_M = 250
_COLLECTION = "MODIS/061/MOD44B"
_GDRIVE_FOLDER = "geometrics_treecover"

_VARIABLE_DEFS = [{"name": "percent_tree_cover", "unit": "percent"}]

SOURCE_SPEC = {
    "name": _SOURCE_NAME,
    "description": "MODIS MOD44B annual percent tree cover",
    "gee_collection": _COLLECTION,
    "pixel_resolution_m": _PIXEL_RESOLUTION_M,
    "native_level": _NATIVE_LEVEL,
    "source_temporal_granularity": "year",
    "temporal_granularity": "year",
    "variables": [
        {
            "name": "percent_tree_cover",
            "unit": "percent",
            "description": "Annual percent tree cover (0–100)",
        },
    ],
}


def submit_treecover(
    engine: Engine,
    config: GeoMetricsConfig,
    backend: GridBackend,
    items: list[dict],
    gdrive_folder: str,
    file_prefix: str,
) -> int:
    """
    Submit one GEE batch job for a batch of missing MODIS treecover items.

    gdrive_folder: Drive folder for this batch (caller sets subfolder per source).
    file_prefix: filename without extension, e.g. "batch_001".
    Returns the local job_id.
    """
    source_id = ensure_source(
        engine=engine,
        name=_SOURCE_NAME,
        native_level=_NATIVE_LEVEL,
        pixel_resolution_m=_PIXEL_RESOLUTION_M,
        source_temporal_granularity="year",
        temporal_granularity="year",
        variable_defs=_VARIABLE_DEFS,
    )

    cells_fc = items_to_ee_feature_collection(backend, items)
    processed = cells_fc.map(_process_feature)

    date_start = min(item["date_start"] for item in items)
    date_end = max(item["date_end"] for item in items)

    task_id = submit_export(
        collection=processed,
        description=f"GeoMetrics Treecover {file_prefix}",
        folder=gdrive_folder,
        file_prefix=file_prefix,
        properties=["cell_id", "variable_name", "timestamp", "value"],
    )

    return record_submitted(
        engine=engine,
        task_id=task_id,
        source_id=source_id,
        level=_NATIVE_LEVEL,
        date_start=date_start,
        date_end=date_end,
        gdrive_folder=gdrive_folder,
        file_prefix=file_prefix,
        gdrive_base=config.gdrive_base,
        row_count=len(items),
    )


def _process_feature(feature):
    """GEE server-side: pick the annual treecover image for each feature's year."""
    import ee

    year = ee.Date(feature.get("start_date")).get("year")

    image = (
        ee.ImageCollection(_COLLECTION)
        .filter(ee.Filter.calendarRange(year, year, "year"))
        .select("Percent_Tree_Cover")
        .first()
    )

    result = image.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=feature.geometry(),
        scale=_PIXEL_RESOLUTION_M,
        maxPixels=1e9,
        bestEffort=True,
    )

    return feature.set({
        "variable_name": "MODIS_Treecover:percent_tree_cover",
        "value": result.get("Percent_Tree_Cover"),
    })
