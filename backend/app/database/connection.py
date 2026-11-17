"""Small, reusable SQLite connection and transaction helpers."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from threading import RLock

_SCHEMA_LOCK = RLock()
_INITIALIZED = {}


def database_path(config=None):
    if config is not None:
        return Path(config["SQLITE_PATH"]).resolve()
    return Path(__file__).resolve().parents[2] / "database" / "aquaintel.db"


def connect(path=None, *, readonly=False):
    target = Path(path or database_path()).resolve()
    if not readonly:
        target.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(target), timeout=30)
    else:
        connection = sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    if not readonly:
        connection.execute("PRAGMA journal_mode = WAL")
    return connection


@contextmanager
def transaction(path=None):
    connection = connect(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(path=None):
    target = Path(path or database_path()).resolve()
    schema = Path(__file__).resolve().parents[2] / "database" / "schema.sql"
    schema_version = schema.stat().st_mtime_ns
    key = str(target)
    with _SCHEMA_LOCK:
        if target.is_file() and _INITIALIZED.get(key) == schema_version:
            return target
        connection = connect(target)
        try:
            connection.executescript(schema.read_text(encoding="utf-8"))
        finally:
            connection.close()
        _INITIALIZED[key] = schema_version
    return target
