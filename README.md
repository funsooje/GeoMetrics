# GeoMetrics

A multi-resolution environmental data store backed by Google Earth Engine (GEE).

GeoMetrics lets you check which (location, variable, timestamp) combinations you already have, submit missing ones to GEE for extraction, and ingest the results — all through a single Python API.

## What it does

- **check** — given a list of locations and timestamps, report what's already in the store and what's missing
- **gee_submit** — submit missing items to GEE as batch export jobs (one job per source per batch)
- **ingest** — scan a Google Drive folder for completed CSVs and load them into the database
- **fetch** — retrieve stored observations as a DataFrame

Timestamps are automatically snapped to each dataset's temporal resolution (e.g. any date in 2023 → `2023-01-01` for annual datasets). Locations are snapped to the underlying HierGP grid so repeated queries for nearby points are deduplicated.

## Supported datasets

| Source | Variable | Resolution | Temporal |
|--------|----------|-----------|----------|
| `Landsat_NDVI` | `NDVI` | 30 m | Annual median (Landsat 5/7/8/9) |
| `MODIS_Treecover` | `percent_tree_cover` | 250 m | Annual (MOD44B) |

## Prerequisites

- Python 3.10+
- PostgreSQL database
- Google Earth Engine account (authenticated via `ee.Initialize()`)
- Google Drive mounted locally (for ingest)

Install dependencies:

```bash
conda env create -f environment.yml
conda activate geometrics
pip install -e .
```

## Setup

### 1. Configure

```python
from geometrics import GeoMetrics

gm = GeoMetrics.configure(
    db_url="postgresql://user:password@localhost:5432/geometrics",
    gdrive_base="/path/to/My Drive",
    backend="hiergp",
)
```

Config is saved to `~/.geometrics/config.json`. Subsequent calls to `GeoMetrics()` load it automatically.

### 2. Initialize the database

```python
gm.init_db()
```

Safe to call on an existing database — creates tables only if they don't exist.

### 3. Register sources

```python
gm.register_sources()
# registered: Landsat_NDVI (1 variable(s))
# registered: MODIS_Treecover (1 variable(s))
```

## Usage

### Prepare your locations CSV

The input file must have at minimum three columns: `latitude`, `longitude`, and `timestamp`.

```
site_id,latitude,longitude,timestamp
WA001,47.6062,-122.3321,2023-07-15T14:30:00
WA002,46.8523,-121.7603,2023-07-15T11:00:00
BR001,-2.4297,-54.7083,2023-08-01T10:00:00
```

### Check availability

```python
import ee
ee.Initialize()

res = gm.check(
    "locations.csv",
    variables=["Landsat_NDVI:NDVI", "MODIS_Treecover:percent_tree_cover"],
)

import pandas as pd
pd.DataFrame(res["available"])
pd.DataFrame(res["missing"])
```

Each row in the output includes the original timestamp alongside the resolved one (`timestamp` → dataset granularity).

### Submit missing items to GEE

```python
job_ids = gm.gee_submit(res["missing"], gdrive_folder="extract-01")
# Landsat_NDVI/batch_001 | 7 (cell, timestamp) pair(s)
#   job_id=1
# MODIS_Treecover/batch_001 | 7 (cell, timestamp) pair(s)
#   job_id=2
```

Files are written to `gdrive_folder/` in Google Drive, named `{Source}_batch_001.csv`, `{Source}_batch_002.csv`, etc.

### Track job status

```python
gm.jobs()          # all jobs
gm.jobs("PENDING") # filter by status

gm.check_status()  # poll GEE and update local status
```

Status values: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`, `EXPIRED`, `INGESTED`

### Ingest completed results

Once GEE jobs show `COMPLETED` and the Drive folder is synced locally:

```python
gm.ingest("extract-01")
# Ingesting Landsat_NDVI_batch_001.csv ...
#   Landsat_NDVI_batch_001.csv: inserted 7 row(s), skipped 0 duplicate(s).
# Ingesting MODIS_Treecover_batch_001.csv ...
#   MODIS_Treecover_batch_001.csv: inserted 7 row(s), skipped 0 duplicate(s).
```

### Fetch stored data

```python
df = gm.fetch(
    "locations.csv",
    variables=["Landsat_NDVI:NDVI", "MODIS_Treecover:percent_tree_cover"],
)
```

Returns a DataFrame with columns: `lat`, `lon`, `timestamp`, `resolved_timestamp`, `source`, `parameter`, `value`, `cell_id`, `level`, `aggregated`.

## API reference

```python
GeoMetrics.configure(db_url, gdrive_base, backend)  # save config, return instance
GeoMetrics.list_sources()                            # catalog metadata for all sources
GeoMetrics.list_variables(source)                   # variables for one source

gm.init_db()                                        # create DB tables
gm.register_sources()                               # register catalog in DB
gm.show_config()                                    # print current config

gm.check(locations, variables, ...)                 # availability check
gm.fetch(locations, variables, ...)                 # retrieve stored data
gm.gee_submit(missing_items, gdrive_folder, batch_size=1000)  # submit to GEE
gm.jobs(status=None)                               # list jobs
gm.check_status()                                  # poll GEE, update DB
gm.ingest(gdrive_folder)                           # load Drive CSVs into DB
```
