"""Дневной отчёт — Claude Sonnet анализирует все звонки за день и пишет связный текст.

Запуск: python daily_report.py
"""
import html
from datetime import datetime, time, timedelta, timezone

from anthropic import Anthropic

import config
import db
import notify


KYIV_TZ = timezone(timedelta(hours=2))


REPORT_PROMPT = """Ти керівник кол-центру ветклініки "Центр". Нижче — дані по всіх проаналізованих дзвінках за сьогодні. Напиши короткий, корисний звіт для власника клініки українською мовою.

Структура звіту (HTML-теги <b>, <i>, <code>, можна emoji):

<b>📊 Загальна картина</b>
2-3 речення: як пройшов день, настрій оцінки (сильний / середній / слабкий день), в порівнянні зі стандартом.

<b>🎯 Головне</b>
3-5 буллетів з найважливішим: що ламається системно, у кого провали, де втрачаються гроші. Будь конкретним: імена операторів, цифри.

<b>🚨 Слиті клієнти</b>
Список тих, хто не записався або був незадоволений. Для кожного: телефон, оператор, 1 речення в чому проблема, що робити (передзвонити? які слова?).

<b>💰 Упущені допродажі</b>
Якщо є — список коротко.

<b>👥 По операторах</b>
Якщо кілька операторів — коротко по кожному: сильні/слабкі сторони, конкретна порада на завтра.

<b>✅ Що зробити керівнику</b>
2-3 конкретні дії на найближчий день. Не загальні ("покращити якість"), а конкретні ("з Оксаною розібрати дзвінок XXXXX — не повторила деталі запису").

Правила:
- Пиши живою українською, як людина керівнику, а не як робот
- Якщо день без проблем — так і скажи, не вигадуй проблем
- Не повторюй очевидне ("було 10 дзвінків" — це вже в заголовку)
- Короткі речення. Без води.
- Телефони в <code>+380...</code>

Дані:
Дата: {date}
Всього дзвінків: {total}
Записались: {booked}, не записались: {not_booked}, нечітко: {unclear}
Середній бал: {avg_pct}
Ризики: 🟢 {r0} / 🟡 {r1} / 🟠 {r2} / 🔴 {r3}

Звінки:
{calls_json}
"""


def _build_calls_data(calls: list[dict]) -> str:
    lines = []
    for c in calls:
        pct = (c["score"] / c["max_score"] * 100) if c.get("max_score") else 0
        booked_str = {1: "так", 0: "ні", -1: "нечітко", None: "нечітко"}.get(c.get("booked"), "нечітко")
        parts = [
            f"— [risk={c['risk']}, {c['score']}/{c['max_score']} ({pct:.0f}%), booked={booked_str}]",
            f"  тел: {c.get('phone') or '—'}, оператор: {c.get('operator') or '—'}",
            f"  summary: {c.get('summary') or '—'}",
        ]
        if c.get("reason"):
            parts.append(f"  reason: {c['reason']}")
        if c.get("missed_upsell"):
            parts.append(f"  missed_upsell: {c['missed_upsell']}")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


def _write_report(calls: list[dict], date_str: str) -> str:
    total = len(calls)
    booked = sum(1 for c in calls if c.get("booked") == 1)
    not_booked = sum(1 for c in calls if c.get("booked") == 0)
    unclear = total - booked - not_booked

    scored = [c for c in calls if c.get("max_score", 0) > 0]
    avg_pct = (
        f"{sum(c['score'] / c['max_score'] for c in scored) / len(scored) * 100:.0f}%"
        if scored else "—"
    )

    r = [0, 0, 0, 0]
    for c in calls:
        risk = c.get("risk", 0)
        if 0 <= risk <= 3:
            r[risk] += 1

    prompt = REPORT_PROMPT.format(
        date=date_str,
        total=total,
        booked=booked,
        not_booked=not_booked,
        unclear=unclear,
        avg_pct=avg_pct,
        r0=r[0], r1=r[1], r2=r[2], r3=r[3],
        calls_json=_build_calls_data(calls),
    )

    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    for block in msg.content:
        if getattr(block, "type", None) == "text":
            return block.text.strip()
    return ""


def main():
    now = datetime.now(KYIV_TZ)
    start = datetime.combine(now.date(), time(0, 0), tzinfo=KYIV_TZ)
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000)

    calls = db.get_today_calls(start_ms, end_ms)
    date_str = now.strftime("%d.%m.%Y")

    if not calls:
        notify.send(f"📊 <b>Підсумки за {date_str}</b>\n\nЗа сьогодні проаналізованих дзвінків немає.")
        return

    header = f"📊 <b>Підсумки за {date_str}</b>  ·  {len(calls)} дзвінків\n\n"
    body = _write_report(calls, date_str)
    notify.send(header + body)


if __name__ == "__main__":
    main()
