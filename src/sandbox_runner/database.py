import sqlite3
import time
from pathlib import Path
from typing import Any
from sandbox_runner.config import DB_FILE, DEFAULT_HISTORY_LIMIT

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp    REAL    NOT NULL,
    language     TEXT    NOT NULL,
    code_snippet TEXT    NOT NULL,
    status       TEXT    NOT NULL,
    exit_code    INTEGER,
    duration_ms  REAL    NOT NULL,
    stdout_size  INTEGER NOT NULL DEFAULT 0,
    stderr_size  INTEGER NOT NULL DEFAULT 0
);
"""

_conn: sqlite3.Connection | None = None


def get_conn()->sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn=sqlite3.connect(str(Path(DB_FILE)),check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute(_CREATE_TABLE)
        _conn.commit()
    return _conn

def record_run(language: str, code_snippet: str, status: str,exit_code: int |None,duration_ms:float,
stdout_size: str,stderr_size:str) -> int:
    """Record a single run into the history table. """
    conn=get_conn()
    code_snippet_for_db=code_snippet[:500]
    cursor=conn.cursor()
    cursor.execute("""
        INSERT INTO runs (timestamp,language,code_snippet,status,exit_code,duration_ms,stdout_size,stderr_size)
        VALUES (?,?,?,?,?,?,?,?)
        """,(time.time(),language,code_snippet_for_db,status,exit_code,duration_ms,len(stdout_size),len(stderr_size)))
    conn.commit()
    return cursor.lastrowid

def fetch_history(limit:int = DEFAULT_HISTORY_LIMIT)->list[dict[str,Any]]:
    """Fetch the recent execution history, ordered from newest to oldest."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT id, timestamp, language, code_snippet, status, exit_code,
               duration_ms, stdout_size, stderr_size
        FROM runs
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]
