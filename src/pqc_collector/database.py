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


def init_query_pages_table(conn):
    """Create the query page storage table."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS query_pages (
            query_page_key TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            query_key TEXT NOT NULL,
            query_group TEXT NOT NULL,
            page INTEGER NOT NULL,
            page_size INTEGER NOT NULL,
            total_count INTEGER NOT NULL,
            item_count INTEGER NOT NULL,
            new_unique_item_count INTEGER NOT NULL,
            duplicate_item_count INTEGER NOT NULL,
            duplicate_ratio REAL NOT NULL,
            raw_path TEXT NOT NULL,
            fetched_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def init_repositories_table(conn):
    """Create the GitHub repository metadata table."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS repositories (
            repository_key TEXT PRIMARY KEY,
            repository_id INTEGER NOT NULL UNIQUE,
            full_name TEXT NOT NULL,
            html_url TEXT NOT NULL,
            first_seen_batch_id TEXT NOT NULL,
            last_seen_batch_id TEXT NOT NULL
        )
        """
    )
    conn.commit()
