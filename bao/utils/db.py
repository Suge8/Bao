from pathlib import Path

import lancedb

_connections: dict[str, lancedb.DBConnection] = {}


def get_db(workspace: Path) -> lancedb.DBConnection:
    key = str(workspace)
    if key not in _connections:
        db_path = workspace / "lancedb"
        db_path.mkdir(parents=True, exist_ok=True)
        _connections[key] = lancedb.connect(str(db_path))
    return _connections[key]


def ensure_table(db: lancedb.DBConnection, name: str, sample: list[dict]) -> lancedb.table.Table:
    try:
        return db.open_table(name)
    except Exception:
        return db.create_table(name, data=sample)
