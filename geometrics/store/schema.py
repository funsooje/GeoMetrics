from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.engine import Engine

metadata = MetaData()

# One row per dataset (e.g. Landsat 8 NDVI, MODIS treecover, ERA5-Land)
sources = Table(
    "sources",
    metadata,
    Column("source_id", Integer, primary_key=True),
    Column("name", Text, nullable=False, unique=True),
    Column("native_level", Integer, nullable=False),
    Column("pixel_resolution_m", Integer, nullable=False),
    # How often the raw source publishes data (e.g. "16-day", "hourly", "year")
    Column("source_temporal_granularity", Text, nullable=True),
    # How we aggregate before storing: year|month|day|hour
    Column("temporal_granularity", Text, nullable=False),
)

# One row per band/variable within a source
variables = Table(
    "variables",
    metadata,
    Column("variable_id", Integer, primary_key=True),
    Column("source_id", Integer, ForeignKey("sources.source_id"), nullable=False),
    Column("name", Text, nullable=False),
    Column("unit", Text),
)

# One row per (cell, variable, time) observation
observations = Table(
    "observations",
    metadata,
    Column("cell_id", Text, nullable=False),
    Column("variable_id", Integer, ForeignKey("variables.variable_id"), nullable=False),
    Column("timestamp", Text, nullable=False),
    Column("value", Float),
    UniqueConstraint("cell_id", "variable_id", "timestamp", name="uq_obs_cell_var_time"),
)

# One row per GEE batch export task
jobs = Table(
    "jobs",
    metadata,
    Column("job_id", Integer, primary_key=True),
    Column("task_id", Text),                                         # GEE task ID
    Column("source_id", Integer, ForeignKey("sources.source_id")),
    Column("level", Integer),
    Column("date_start", Text),
    Column("date_end", Text),
    Column("gdrive_folder", Text),
    Column("file_prefix", Text),
    Column("expected_path", Text),                                   # set at submit time
    # PENDING | RUNNING | COMPLETED | FAILED | CANCELLED | EXPIRED | INGESTED
    # EXPIRED: GEE no longer knows the task and it never confirmed COMPLETED
    Column("status", Text, nullable=False, default="PENDING"),
    Column("submitted_at", Text),
    Column("completed_at", Text),
    Column("ingested_at", Text),
    Column("row_count", Integer),
)


def initialize_db(engine: Engine) -> None:
    metadata.create_all(engine)
    print(f"Initialised schema on {engine.url.render_as_string(hide_password=True)}")
