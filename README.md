# GeoMetrics

A multi-resolution environmental data store backed by Google Earth Engine (GEE), with a built-in map viewer for exploration.

GeoMetrics solves a common research problem: you have a list of field sites and dates, and you need environmental covariates — vegetation indices, land cover, climate, water proximity — for each one. Pulling that data manually from different sources is slow and produces inconsistent spatial representations. GeoMetrics automates the full pipeline: it snaps your locations to a consistent spatial grid, checks what you already have in the database, submits missing extractions to GEE as batch jobs, ingests the results, and serves them back as a clean DataFrame.

---

## How it works

```
Your locations CSV
       │
       ▼
  [snap to grid]          ← HierGP rectangular grid, resolution-aware
       │
       ▼
  [check store]           ← which (cell, variable, year) are already cached?
       │
       ├─── available ─── gm.fetch() ──► DataFrame
       │
       └─── missing ──── gm.gee_submit() ──► GEE batch export jobs
                                │
                         (jobs run in GEE)
                                │
                         gm.ingest() ──► PostgreSQL
                                │
                         gm.fetch()  ──► DataFrame
```

**Spatial grid.** All sources share a common HierGP rectangular grid. Each location is snapped to the nearest cell at the source's native resolution, so repeated queries for nearby points are automatically deduplicated and every dataset lines up spatially.

**Temporal snapping.** Timestamps are resolved to each dataset's temporal granularity — any date in 2023 maps to `2023-01-01` for annual datasets, to the nearest hour for ERA5-Land, and so on.

**Backend-agnostic.** The grid layer is pluggable. HierGP (rectangular) is the default; H3 (hexagonal) is also supported. The rest of the system — schema, ingest, query — works identically regardless of backend.

---

## Supported datasets

| Source | Variable(s) | Native resolution | Temporal | GEE collection |
|--------|-------------|:-----------------:|----------|----------------|
| `Landsat_NDVI` | `NDVI` | 30 m | Annual median | Landsat 5/7/8/9 (USGS SR) |
| `MODIS_NDVI` | `NDVI` | 250 m | Annual | MOD13Q1 |
| `MODIS_Treecover` | `percent_tree_cover`, `percent_nontree_vegetation`, `percent_nonvegetated`, `quality`, `percent_tree_cover_sd`, `percent_nonvegetated_sd`, `cloud` | 250 m | Annual | MOD44B |
| `ERA5_Land` | `temperature_2m`, `dewpoint_temperature_2m`, `surface_pressure`, `u_component_of_wind_10m`, `v_component_of_wind_10m`, `surface_thermal_radiation_downwards`, `surface_net_solar_radiation`, `total_precipitation` | ~9 km | Hourly | ERA5-Land (ECMWF) |
| `JRC_Water` | `water_distance` | 30 m | Annual | JRC Global Surface Water |
| `YALE_UHI` | `yearly_daytime`, `yearly_nighttime`, `winter_daytime`, `winter_nighttime`, `summer_daytime`, `summer_nighttime` | 1 km | Annual | Yale Urban Heat Island |
| `NLCD` | `landcover`, `impervious`, `impervious_descriptor` | 30 m | Annual | NLCD (USGS) |

---

## Prerequisites

- Python 3.10+
- PostgreSQL 14+ database
- Google Earth Engine account with project access (`ee.Initialize()`)
- Google Drive mounted locally (for ingest step only)

---

## Installation

```bash
conda env create -f environment.yml
conda activate geometrics
pip install -e .
```

---

## Setup

### 1. Configure

Run once. Saves connection settings to `~/.geometrics/config.json`.

```python
from geometrics import GeoMetrics

gm = GeoMetrics.configure(
    db_url="postgresql://user:password@localhost:5432/geometrics",
    gdrive_base="/path/to/My Drive",
    backend="hiergp",
)
```

All subsequent calls to `GeoMetrics()` load the saved config automatically.

### 2. Initialize the database

```python
gm = GeoMetrics()
gm.init_db()
# Database initialized.
# Registered 7 new source(s): ['Landsat_NDVI', 'MODIS_NDVI', ...]
```

Safe to call on an existing database — creates tables only if they don't exist, and skips sources that are already registered.

---

## Core workflow

### Prepare your locations CSV

At minimum, three columns are required. Column names are configurable.

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

gm = GeoMetrics()
report = gm.check(
    "locations.csv",
    variables=["Landsat_NDVI:NDVI", "MODIS_Treecover:percent_tree_cover"],
)

# report["available"] — already in the store
# report["missing"]   — need to be extracted from GEE
```

Each row in both lists includes the original coordinates, the resolved grid cell, the requested timestamp, and the resolved timestamp.

### Submit missing items to GEE

```python
job_ids = gm.gee_submit(report["missing"], gdrive_folder="extract-01")
# Submitted 2 job(s). Track with: gm.jobs()
```

GEE runs the export tasks asynchronously. Results are written as CSVs to the specified Drive folder.

### Track job status

```python
gm.jobs()               # DataFrame of all submitted jobs
gm.jobs("RUNNING")      # filter by status

gm.check_status()       # poll GEE and update local DB
```

Status values: `PENDING` → `RUNNING` → `COMPLETED` / `FAILED` / `CANCELLED` / `EXPIRED` → `INGESTED`

### Ingest completed results

Once GEE jobs are `COMPLETED` and the Drive folder has synced locally:

```python
gm.ingest("extract-01")
# Ingesting Landsat_NDVI_batch_001.csv ... inserted 7 row(s), skipped 0 duplicate(s).
# Ingesting MODIS_Treecover_batch_001.csv ... inserted 7 row(s), skipped 0 duplicate(s).
```

Re-running ingest is safe — duplicates are detected and skipped.

### Fetch stored data

```python
df = gm.fetch(
    "locations.csv",
    variables=["Landsat_NDVI:NDVI", "MODIS_Treecover:percent_tree_cover"],
)
```

Returns a DataFrame joined back to your original input, with one column per variable. Rows with no data are `NaN` by default.

**Output format options:**

```python
# Long format (one row per location × variable)
df = gm.fetch("locations.csv", variables=[...], output_format="long")

# Drop rows with no data at all
df = gm.fetch("locations.csv", variables=[...], preserve_rows=False)

# Strip extra input columns from output
df = gm.fetch("locations.csv", variables=[...], preserve_cols=False)

# Long format with grid metadata
df = gm.fetch("locations.csv", variables=[...],
               output_format="long", include_metadata=True)
# Extra columns: cell_id, level, aggregated, resolved_timestamp
```

---

## Map viewer

GeoMetrics ships a browser-based map viewer for exploring what's in the database.

```bash
python viewer/server.py
# or with live reload:
uvicorn viewer.server:app --reload --port 8765
```

Open `http://localhost:8765` in your browser.

**Features:**
- Browse all sources, variables, and available years from a sidebar
- Load up to 200,000 cells for the full dataset or just the current viewport ("Load focus area")
- Circle radius scales with the dataset's spatial resolution
- 12 colormaps (Viridis, Greens, NDVI Red→Green, Blues, Plasma, Inferno, Magma, Yellow→Red, Spectral, Cividis, Hot, Greys)
- Adjustable opacity
- Hover tooltip showing value and coordinates
- Auto-updating legend with data min/max

The viewer API is also accessible directly:
- `GET /api/sources` — all sources with variables and available timestamps
- `GET /api/data?source=&variable=&timestamp=&bbox=` — cell data for a selection

---

## API reference

### Configuration and setup

```python
GeoMetrics.configure(db_url, gdrive_base, backend)  # save config, return instance
gm.show_config()                                     # print current config as dict
gm.init_db()                                         # create tables + register sources
gm.register_sources()                                # register/update catalog in DB
```

### Discovery

```python
GeoMetrics.list_sources()          # list[dict] — all catalog entries
GeoMetrics.list_variables(source)  # list[dict] — variables for one source
gm.jobs(status=None)               # DataFrame of submitted jobs
```

### Data pipeline

```python
gm.check(locations, variables, lat_col, lon_col, timestamp_col)
# → {"available": [...], "missing": [...]}

gm.gee_submit(missing_items, gdrive_folder, batch_size=1000)
# → list[int] of job_ids

gm.check_status()
# → {status: count} summary dict

gm.ingest(gdrive_folder)
# → {filename: rows_inserted}

gm.fetch(locations, variables, lat_col, lon_col, timestamp_col,
         output_format="wide", preserve_rows=True, preserve_cols=True,
         include_metadata=False)
# → pd.DataFrame
```

### Maintenance

```python
gm.clear(source)       # drop all observations for a source (keeps schema)
gm.reset_db()          # drop all observation tables and reinitialize
```

---

## Architecture

### Spatial grid

GeoMetrics uses HierGP, a recursive rectangular grid with a base cell size of 25 m. The grid has 15 levels:

| Standard level | Cell size | Typical use |
|:--------------:|-----------|-------------|
| 15 | 25 m | Finest — high-res imagery |
| 14 | 50 m | |
| 13 | 100 m | |
| 12 | 200 m | |
| 11 | 400 m | |
| 10 | 800 m | |
| 9 | 1.6 km | |
| ... | ... | |
| 1 | ~410 km | Coarsest |

Each source is registered with a `native_level` that matches its pixel footprint. Locations are snapped to that level, so two sites that fall in the same 100 m cell share a single database row for that source.

### Database schema

```
sources              — one row per dataset (name, native_level, pixel_resolution_m, ...)
variables            — one row per band within a source (name, unit)
cells                — one row per unique grid cell (cell_id, backend, level)
hiergp_cells         — HierGP-specific: x/y integer coordinates for each cell
spatiotemporal_units — one row per (cell × timestamp) pair; RANGE-partitioned by year
obs_{source_name}    — wide observation table: unit_pk + one column per variable
jobs                 — GEE export task registry (status, file paths, row counts)
```

The observation tables are intentionally denormalized (wide format) so that fetching multiple variables for the same location requires only one join. The `spatiotemporal_units` table is partitioned by year in PostgreSQL for fast range scans.

### Adding a new source

1. Create `geometrics/extraction/my_source.py` and define a `SOURCE_SPEC` dict and a `build_ee_image()` function following the pattern in `geometrics/extraction/ndvi.py`.
2. Import `SOURCE_SPEC` in `geometrics/catalog.py` and add it to `CATALOG`.
3. Run `gm.register_sources()` to add the source and its variables to the database.

---

## License

See [LICENSE](LICENSE).
