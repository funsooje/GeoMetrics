"""
Static registry of all implemented GEE extraction sources.

Each extraction module exports a SOURCE_SPEC dict; this module collects them
into CATALOG for use by the CLI and any code that needs to discover sources
without touching the database.
"""

from __future__ import annotations

from geometrics.extraction.era5_land import SOURCE_SPEC as _ERA5_LAND_SPEC
from geometrics.extraction.modis_ndvi import SOURCE_SPEC as _MODIS_NDVI_SPEC
from geometrics.extraction.ndvi import SOURCE_SPEC as _NDVI_SPEC
from geometrics.extraction.treecover import SOURCE_SPEC as _TREECOVER_SPEC
from geometrics.extraction.nlcd import SOURCE_SPEC as _NLCD_SPEC
from geometrics.extraction.uhi import SOURCE_SPEC as _UHI_SPEC
from geometrics.extraction.water import SOURCE_SPEC as _WATER_SPEC

CATALOG: dict[str, dict] = {
    spec["name"]: spec
    for spec in [
        _NDVI_SPEC, _MODIS_NDVI_SPEC, _TREECOVER_SPEC,
        _ERA5_LAND_SPEC, _WATER_SPEC, _UHI_SPEC, _NLCD_SPEC,
    ]
}


def get_source(name: str) -> dict:
    if name not in CATALOG:
        known = ", ".join(CATALOG)
        raise ValueError(f"Unknown source {name!r}. Available: {known}")
    return CATALOG[name]
