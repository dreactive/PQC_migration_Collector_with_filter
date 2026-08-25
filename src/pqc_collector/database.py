import sqlite3
from pathlib import Path

from pqc_collector.util import project_paths


def connect(path=None, root=None):
    """Open a SQLite connection for collector storage."""
    db_path = path if path is not None else project_paths(root)["data"] / "collector.sqlite"
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
