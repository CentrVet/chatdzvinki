import sqlite3
from contextlib import contextmanager

import config


SCHEMA = """
CREATE TABLE IF NOT EXISTS processed (
    uuid TEXT PRIMARY KEY,
    processed_at INTEGER NOT NULL,
    risk INTEGER,
    score INTEGER,
    max_score INTEGER,
    phone TEXT,
    operator TEXT,
    summary TEXT,
    reason TEXT
);
"""


def _migrate(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(processed)").fetchall()}
    for col, ddl in [
        ("max_score", "ALTER TABLE processed ADD COLUMN max_score INTEGER"),
        ("summary", "ALTER TABLE processed ADD COLUMN summary TEXT"),
        ("reason", "ALTER TABLE processed ADD COLUMN reason TEXT"),
        ("booked", "ALTER TABLE processed ADD COLUMN booked INTEGER"),  # 1/0/-1(null)
        ("missed_upsell", "ALTER TABLE processed ADD COLUMN missed_upsell TEXT"),
    ]:
        if col not in cols:
            conn.execute(ddl)


@contextmanager
def connect():
    conn = sqlite3.connect(config.DB_PATH)
    try:
        conn.execute(SCHEMA)
        _migrate(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def is_processed(uuid: str) -> bool:
    with connect() as c:
        row = c.execute("SELECT 1 FROM processed WHERE uuid = ?", (uuid,)).fetchone()
        return row is not None


def mark_processed(uuid: str, processed_at: int, risk: int, score: int, phone: str,
                   operator: str, max_score: int = 0, summary: str = "", reason: str = "",
                   booked=None, missed_upsell=None):
    booked_i = -1 if booked is None else (1 if booked else 0)
    with connect() as c:
        c.execute(
            """INSERT OR REPLACE INTO processed
               (uuid, processed_at, risk, score, max_score, phone, operator, summary, reason,
                booked, missed_upsell)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (uuid, processed_at, risk, score, max_score, phone, operator, summary, reason,
             booked_i, missed_upsell),
        )


def get_today_calls(start_ms: int, end_ms: int) -> list[dict]:
    """Все звонки, обработанные сегодня (risk != -1 — не пропущенные)."""
    with connect() as c:
        rows = c.execute(
            """SELECT uuid, processed_at, risk, score, max_score, phone, operator, summary, reason,
                      booked, missed_upsell
               FROM processed
               WHERE processed_at BETWEEN ? AND ? AND risk >= 0
               ORDER BY risk DESC, score ASC""",
            (start_ms, end_ms),
        ).fetchall()
    cols = ["uuid", "processed_at", "risk", "score", "max_score", "phone", "operator",
            "summary", "reason", "booked", "missed_upsell"]
    return [dict(zip(cols, r)) for r in rows]
