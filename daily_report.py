"""Дневной отчёт — Claude Sonnet анализирует все звонки за день и пишет связный текст.

Запуск: python daily_report.py
"""
from collections import Counter
from datetime import datetime, time, timedelta, timezone

from anthropic import Anthropic

import config
import db
import notify


KYIV_TZ = timezone(timedelta(hours=2))


REPORT_PROMPT = """Ти керівник кол-центру ветклініки "Центр". Нижче — дані по всіх проаналізованих дзвінках за сьогодні. Напиши короткий, корисний звіт для власника клініки українською мовою.

Структура звіту (HTML-теги <b>, <i>, <code>, можна emoji):

<b>📊 Загальна картина</b>
2-3 речення: як пройшов день — вхідні + вихідні + пропущені разом. Загальний настрій (сильний / середній / слабкий день).

<b>📞 Пропущені дзвінки</b>
Якщо є: загальна кількість, пікові години (якщо помітно скупчення), 1-2 речення чому це проблема. Якщо немає — пропустити блок.

<b>🎯 Головне</b>
3-5 буллетів з найважливішим: що ламається системно, у кого провали, де втрачаються гроші. Будь конкретним: імена операторів, цифри.

<b>🚨 Слиті клієнти (вхідні)</b>
Список тих, хто не записався або був незадоволений. Для кожного: телефон, оператор, 1 речення в чому проблема, що робити.

<b>📤 Вихідні з червоними прапорцями</b>
Якщо є вихідні з risk >= 2 — список: телефон, оператор, 1 речення що сталось, що робити. Якщо все ок — одна фраза "вихідні без проблем".

<b>💰 Упущені допродажі</b>
Тільки якщо є (вхідні з missed_upsell).

<b>👥 По операторах</b>
По кожному: вхідні/вихідні окремо, сильні/слабкі сторони, конкретна порада на завтра.

<b>✅ Що зробити керівнику</b>
2-3 конкретні дії на найближчий день.

Правила:
- Пиши живою українською, як людина керівнику
- Не вигадуй проблем якщо день без проблем
- Короткі речення. Без води.
- Телефони в <code>+380...</code>

Дані:
Дата: {date}

ВХІДНІ (проаналізовано: {in_total})
Записались: {booked}, не записались: {not_booked}, нечітко: {unclear}
Середній бал: {avg_pct}
Ризики: 🟢 {in_r0} / 🟡 {in_r1} / 🟠 {in_r2} / 🔴 {in_r3}

ВИХІДНІ (проаналізовано: {out_total})
Ризики: 🟢 {out_r0} / 🟡 {out_r1} / 🟠 {out_r2} / 🔴 {out_r3}

ПРОПУЩЕНІ ВХІДНІ: {missed_total}
Розподіл по годинах (Київ): {missed_hours}

Вхідні звінки:
{in_calls}

Вихідні звінки:
{out_calls}

Приклади номерів пропущених (до 10):
{missed_phones}
"""


def _in_call_str(c: dict) -> str:
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
    return "\n".join(parts)


def _out_call_str(c: dict) -> str:
    parts = [
        f"— [risk={c['risk']}]",
        f"  тел: {c.get('phone') or '—'}, оператор: {c.get('operator') or '—'}",
        f"  summary: {c.get('summary') or '—'}",
    ]
    if c.get("reason"):
        parts.append(f"  reason: {c['reason']}")
    return "\n".join(parts)


def _write_report(incoming: list[dict], outgoing: list[dict], missed: list[dict], date_str: str) -> str:
    booked = sum(1 for c in incoming if c.get("booked") == 1)
    not_booked = sum(1 for c in incoming if c.get("booked") == 0)
    unclear = len(incoming) - booked - not_booked

    scored = [c for c in incoming if c.get("max_score", 0) > 0]
    avg_pct = (
        f"{sum(c['score'] / c['max_score'] for c in scored) / len(scored) * 100:.0f}%"
        if scored else "—"
    )

    in_r = [0, 0, 0, 0]
    for c in incoming:
        if 0 <= c.get("risk", 0) <= 3:
            in_r[c["risk"]] += 1
    out_r = [0, 0, 0, 0]
    for c in outgoing:
        if 0 <= c.get("risk", 0) <= 3:
            out_r[c["risk"]] += 1

    # Распределение пропущенных по часам
    hours = Counter()
    for c in missed:
        dt = datetime.fromtimestamp(c["processed_at"] / 1000, tz=KYIV_TZ)
        hours[dt.hour] += 1
    missed_hours = (
        ", ".join(f"{h:02d}:00→{n}" for h, n in sorted(hours.items())) or "—"
    )
    missed_phones = "\n".join(f"— {c.get('phone') or '—'}" for c in missed[:10]) or "—"

    prompt = REPORT_PROMPT.format(
        date=date_str,
        in_total=len(incoming),
        booked=booked, not_booked=not_booked, unclear=unclear,
        avg_pct=avg_pct,
        in_r0=in_r[0], in_r1=in_r[1], in_r2=in_r[2], in_r3=in_r[3],
        out_total=len(outgoing),
        out_r0=out_r[0], out_r1=out_r[1], out_r2=out_r[2], out_r3=out_r[3],
        missed_total=len(missed),
        missed_hours=missed_hours,
        in_calls="\n\n".join(_in_call_str(c) for c in incoming) or "—",
        out_calls="\n\n".join(_out_call_str(c) for c in outgoing) or "—",
        missed_phones=missed_phones,
    )

    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )
    parts = [b.text for b in msg.content if getattr(b, "type", None) == "text"]
    text = "\n".join(parts).strip()
    if not text:
        return f"(звіт не згенеровано, stop_reason={msg.stop_reason})"
    return text


def main():
    now = datetime.now(KYIV_TZ)
    start = datetime.combine(now.date(), time(0, 0), tzinfo=KYIV_TZ)
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000)

    calls = db.get_today_calls(start_ms, end_ms)
    missed = db.get_today_missed(start_ms, end_ms)
    date_str = now.strftime("%d.%m.%Y")

    incoming = [c for c in calls if c.get("kind") in ("in", None, "")]  # None/"" — старые записи до миграции
    outgoing = [c for c in calls if c.get("kind") == "out"]

    if not calls and not missed:
        notify.send(f"📊 <b>Підсумки за {date_str}</b>\n\nЗа сьогодні активності не було.")
        return

    header = (
        f"📊 <b>Підсумки за {date_str}</b>  ·  "
        f"📥{len(incoming)}  📤{len(outgoing)}  📞×{len(missed)}\n\n"
    )
    body = _write_report(incoming, outgoing, missed, date_str)
    notify.send(header + body)


if __name__ == "__main__":
    main()
