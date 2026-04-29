import json
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".geometrics" / "config.json"


@dataclass
class GeoMetricsConfig:
    db_url: str = "sqlite:///geometrics.db"
    gdrive_base: str = ""
    backend: str = "hiergp"


def load_config(path: str | Path | None = None) -> GeoMetricsConfig:
    resolved = Path(path) if path else DEFAULT_CONFIG_PATH
    if not resolved.exists():
        return GeoMetricsConfig()
    with open(resolved) as f:
        data = json.load(f)
    return GeoMetricsConfig(**data)


def save_config(config: GeoMetricsConfig, path: str | Path | None = None) -> None:
    resolved = Path(path) if path else DEFAULT_CONFIG_PATH
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with open(resolved, "w") as f:
        json.dump(asdict(config), f, indent=2)
