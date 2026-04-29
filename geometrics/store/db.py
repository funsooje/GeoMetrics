from sqlalchemy import Engine, create_engine

_engine: Engine | None = None


def get_engine(db_url: str) -> Engine:
    global _engine
    if _engine is None or _engine.url.render_as_string(hide_password=False) != db_url:
        _engine = create_engine(db_url)
    return _engine
