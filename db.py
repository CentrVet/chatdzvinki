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
        # kind: "in" (вх. проанализирован), "out" (исх. проанализирован),
        #       "missed" (вх. пропущен), "no_answer" (исх. без ответа),
        #       "short" (слишком короткий), "no_audio" (нет записи)
        ("kind", "ALTER TABLE processed ADD COLUMN kind TEXT"),
        # dismissed: причина, по которой пользователь пометил звонок как "не проблема".
        # NULL = активный, не-NULL = исключать из отчётов.
        ("dismissed", "ALTER TABLE processed ADD COLUMN dismissed TEXT"),
        # source: звідки клієнт дізнався про клініку (google, instagram, рекомендація, тощо).
        # NULL = не було в розмові або повторний клієнт.
        ("source", "ALTER TABLE processed ADD COLUMN source TEXT"),
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
                   booked=None, missed_upsell=None, kind: str = "", source: str | None = None):
    booked_i = -1 if booked is None else (1 if booked else 0)
    with connect() as c:
        c.execute(
            """INSERT OR REPLACE INTO processed
               (uuid, processed_at, risk, score, max_score, phone, operator, summary, reason,
                booked, missed_upsell, kind, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (uuid, processed_at, risk, score, max_score, phone, operator, summary, reason,
             booked_i, missed_upsell, kind, source),
        )


COLS = ["uuid", "processed_at", "risk", "score", "max_score", "phone", "operator",
        "summary", "reason", "booked", "missed_upsell", "kind", "dismissed", "source"]


def get_today_calls(start_ms: int, end_ms: int, include_dismissed: bool = False) -> list[dict]:
    """Проанализированные за день звонки (входящие+исходящие с риском >= 0).
    По умолчанию исключает dismissed (помеченные как "не проблема")."""
    extra = "" if include_dismissed else " AND dismissed IS NULL"
    with connect() as c:
        rows = c.execute(
            f"""SELECT {', '.join(COLS)}
                FROM processed
                WHERE processed_at BETWEEN ? AND ? AND risk >= 0{extra}
                ORDER BY risk DESC, score ASC""",
            (start_ms, end_ms),
        ).fetchall()
    return [dict(zip(COLS, r)) for r in rows]


def set_dismissed(uuid: str, reason: str) -> None:
    with connect() as c:
        c.execute("UPDATE processed SET dismissed = ? WHERE uuid = ?", (reason, uuid))


def get_today_missed(start_ms: int, end_ms: int) -> list[dict]:
    """Пропущенные входящие за день."""
    with connect() as c:
        rows = c.execute(
            f"""SELECT {', '.join(COLS)}
                FROM processed
                WHERE processed_at BETWEEN ? AND ? AND kind = 'missed'
                ORDER BY processed_at DESC""",
            (start_ms, end_ms),
        ).fetchall()
    return [dict(zip(COLS, r)) for r in rows]
