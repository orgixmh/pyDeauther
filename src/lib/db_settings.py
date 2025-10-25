# ./lib/db_settings.py
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

# ---------- Module configuration ----------

_DB_PATH: Optional[Path] = None

def configure(db_path: Union[str, Path]) -> None:
    """Set the SQLite file to use for settings."""
    global _DB_PATH
    _DB_PATH = Path(db_path)

# ---------- Internal helpers ----------

def _require_db_path() -> Path:
    if _DB_PATH is None:
        # Default to ./config.sqlite if not configured
        configure("config.sqlite")
    return _DB_PATH  # type: ignore[return-value]

def _connect() -> sqlite3.Connection:
    path = _require_db_path()
    conn = sqlite3.connect(str(path))
    _ensure_table(conn)
    return conn

def _ensure_table(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()

def _to_db_value(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return ""
    return str(value)

def _from_db_value(raw: Optional[str], cast: Optional[Union[str, Callable[[str], Any]]]) -> Any:
    if raw is None:
        return None
    if cast is None:
        return raw
    if callable(cast):
        return cast(raw)

    c = cast.lower()
    if c == "bool":
        return raw.strip().lower() in ("1", "true", "yes", "y", "on")
    if c == "int":
        return int(raw.strip() or "0")
    if c == "float":
        return float(raw.strip() or "0")
    if c == "json":
        return json.loads(raw) if raw.strip() else None
    # default: no cast
    return raw

# ---------- Public API ----------

def get_setting(key: str, default: Any = None, cast: Optional[Union[str, Callable[[str], Any]]] = None) -> Any:
    """
    Read a setting by key.
    - default: returned if key does not exist (not written to DB).
    - cast: 'bool' | 'int' | 'float' | 'json' | callable(str)->Any
    """
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
        if row is None:
            return default
        return _from_db_value(row[0], cast)
    finally:
        conn.close()

# alias to match your requested name
getSettingFromDB = get_setting

def set_setting(key: str, value: Any) -> None:
    """
    Upsert a setting. Booleans stored as '1'/'0'; dict/list stored as JSON; None -> ''.
    """
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, _to_db_value(value)),
        )
        conn.commit()
    finally:
        conn.close()

def get_all_settings(cast_map: Optional[Dict[str, Union[str, Callable[[str], Any]]]] = None) -> Dict[str, Any]:
    """
    Return all settings as a dict. Optionally apply casts per key via cast_map.
    Example: cast_map={'fast_mode':'bool','retries':'int'}
    """
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT key, value FROM settings")
        rows = cur.fetchall()
    finally:
        conn.close()

    result: Dict[str, Any] = {}
    for k, v in rows:
        caster = cast_map.get(k) if cast_map else None
        result[k] = _from_db_value(v, caster)
    return result

def delete_setting(key: str) -> None:
    """Remove a setting key (no error if absent)."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM settings WHERE key = ?", (key,))
        conn.commit()
    finally:
        conn.close()

