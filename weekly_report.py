"""Тижневий звіт — канали залучення клієнтів (звідки дізналися про клініку).

Запуск:
    python weekly_report.py                 # останні 7 днів до сьогодні
    python weekly_report.py --days 14       # останні 14 днів
    python weekly_report.py --from 2026-10-13 --to 2026-10-19
"""
import argparse
import sqlite3
from collections import Counter
from datetime import date as date_cls, datetime, time, timedelta, timezone

import config
import notify


KYIV_TZ = timezone(timedelta(hours=2))


def _fetch(start_ms: int, end_ms: int):
    with sqlite3.connect(config.DB_PATH) as c:
        rows = c.execute(
            """SELECT source, operator, kind, phone FROM processed
               WHERE processed_at BETWEEN ? AND ?
                 AND dismissed IS NULL
                 AND kind IN ('in', 'out')""",
            (start_ms, end_ms),
        ).fetchall()
    return rows


def _bar(n: int, total: int, width: int = 10) -> str:
    if total <= 0:
        return ""
    filled = round(n / total * width)
    return "█" * filled + "·" * (width - filled)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--from", dest="date_from", help="YYYY-MM-DD")
    parser.add_argument("--to", dest="date_to", help="YYYY-MM-DD")
    args = parser.parse_args()

    now = datetime.now(KYIV_TZ)
    if args.date_from and args.date_to:
        d_from = date_cls.fromisoformat(args.date_from)
        d_to = date_cls.fromisoformat(args.date_to)
    else:
        d_to = now.date()
        d_from = d_to - timedelta(days=args.days - 1)

    start = datetime.combine(d_from, time(0, 0), tzinfo=KYIV_TZ)
    end = datetime.combine(d_to, time(23, 59, 59), tzinfo=KYIV_TZ)
    if end > now:
        end = now
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)

    rows = _fetch(start_ms, end_ms)
    total = len(rows)
    with_src = [r for r in rows if r[0]]
    sources = Counter(r[0] for r in with_src)
    coverage = len(with_src) / total * 100 if total else 0

    period = (
        d_from.strftime("%d.%m")
        if d_from == d_to
        else f"{d_from.strftime('%d.%m')}–{d_to.strftime('%d.%m.%Y')}"
    )

    lines = [
        f"📍 <b>Канали залучення · {period}</b>",
        "",
        f"Усього дзвінків: <b>{total}</b> · із зазначеним джерелом: <b>{len(with_src)}</b> ({coverage:.0f}%)",
        "",
    ]

    if sources:
        total_src = sum(sources.values())
        lines.append("<b>Розподіл:</b>")
        for src, n in sources.most_common():
            pct = n / total_src * 100
            lines.append(f"  {_bar(n, total_src)}  <b>{src}</b> — {n} ({pct:.0f}%)")
        lines.append("")

    missing = total - len(with_src)
    if missing:
        lines.append(
            f"<i>У {missing} дзвінках джерело не прозвучало (оператор не спитав або повторний клієнт).</i>"
        )

    if coverage < 30:
        lines.append("")
        lines.append(
            "⚠️ Низьке покриття — варто додати до скрипта оператора питання "
            "«звідки про нас дізналися?» у кінці розмови з новими клієнтами."
        )

    notify.send("\n".join(lines))


if __name__ == "__main__":
    main()
