"""Дневной отчёт — Claude Sonnet анализирует все звонки за день и пишет связный текст.

Запуск: python daily_report.py            # за сьогодні
        python daily_report.py --yesterday
        python daily_report.py --date 2026-10-19
"""
import argparse
import sqlite3
from collections import Counter, defaultdict
from datetime import date as date_cls, datetime, time, timedelta, timezone

from anthropic import Anthropic

import config
import db
import notify


KYIV_TZ = timezone(timedelta(hours=2))


REPORT_PROMPT = """Ти керівник кол-центру ветклініки "ЦентрВет". Нижче — дані по всіх проаналізованих дзвінках за сьогодні. Напиши короткий, корисний звіт для власника клініки українською мовою.

Структура звіту (HTML-теги <b>, <i>, <code>, можна emoji):

<b>📊 Загальна картина</b>
2-3 речення: як пройшов день — вхідні + вихідні + пропущені разом. Загальний настрій (сильний / середній / слабкий день).

<b>📞 Пропущені дзвінки</b>
Якщо є: загальна кількість, пікові години (якщо помітно скупчення), 1-2 речення чому це проблема. Якщо немає — пропустити блок.

<b>🎯 Головне</b>
3-5 буллетів з найважливішим: що ламається системно, у кого провали, де втрачаються гроші. Будь конкретним: імена операторів, цифри.

<b>🚨 Слиті клієнти (вхідні)</b>
ВКЛЮЧАЙ сюди ТІЛЬКИ клієнтів, що були ЯВНО незадоволені (risk=2+ з реальним негативом від клієнта — скарга, обурення, згадка конкурентів). Клієнти, що просто "подумають і передзвонять" БЕЗ висловленого невдоволення — НЕ слиті, їх не включай. Якщо справжніх слитих немає — одна фраза "вхідні без явних втрат".

<b>📤 Вихідні з червоними прапорцями</b>
Якщо є вихідні з risk >= 2 — список: телефон, оператор, 1 речення що сталось, що робити. Якщо все ок — одна фраза "вихідні без проблем".

<b>💰 Упущені допродажі</b>
Тільки якщо є (вхідні з missed_upsell).

<b>👥 По операторах</b>
По кожному: вхідні/вихідні окремо, сильні/слабкі сторони, конкретна порада на завтра.

<b>✅ Що зробити керівнику</b>
Максимум 2-3 РЕАЛЬНІ дії. Якщо день нормальний — пиши "все ок, системних проблем немає". Не вигадуй рекомендацій заради обсягу.

Правила:
- Пиши живою українською, як людина керівнику
- Не вигадуй проблем якщо день без проблем
- Короткі речення. Без води.
- Телефони в <code>+380...</code>
- Назва клініки — "ЦентрВет". Whisper перекручує її ("Сан-Телевед", "Інтервет", "Центравет" і т.п.) — це НЕ помилка оператора.
- Лікарі передзвонюють клієнтам у вільний момент протягом дня — це нормально. Клієнта, який чекає передзвону, не вважай слитим і не пиши "домогтися дзвінка сьогодні". Пиши "передати лікарю нагадування, зв'яжеться у вільний момент" або "уточнити у лікаря, коли він планує передзвін".
- Чесна відмова адміна ("сьогодні не можемо", "спочатку УЗД, потім процедура") — ПРОФЕСІЙНА поведінка, не слив клієнта. Не включай таких клієнтів у "слиті", не пиши "повернути". Якщо хочеш згадати — у позитивному ключі ("адмін чесно скерував клієнта на правильний шлях").
- НЕ рекомендуй дій, які клініка не може гарантувати ("їдьте зараз", "перенести на раніше"). Пиши "передзвонити й уточнити реальний найкоротший час".
- Для кожного ризикового або незаписаного дзвінка в даних є поле "передзвін:" — бот перевірив, чи був вихідний з клініки на цей номер пізніше того ж дня.
  * Якщо "передзвонювали" — НЕ пиши "передзвонити клієнту", передзвін вже був. Пиши про результат ("перевірити результат передзвону" якщо треба).
  * Якщо "НЕ передзвонювали (за даними бота)" — це тільки по Phonet. Передзвін міг бути через viber/особисто. Формулюй: "за даними бота передзвін не зафіксовано — уточнити у [оператор], чи зв'язувались іншим каналом".
  * Пропущені дзвінки — так само: поряд із номером у списку є мітка про передзвін.
- Якщо клієнт має 2+ скарги поспіль і фрази типу "більше не звертатимусь" — не став це головною рекомендацією керівнику "повернути". Такого клієнта не завжди можна і треба повертати. Формулюй: "зафіксувати, за можливості — одноразовий жест (вибачення/компенсація), але не вкладати ресурс у повернення".

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


def _norm_phone(p: str | None) -> str:
    """Нормалізація: тільки цифри, останні 10 (щоб +380XX і 0XX співпадали)."""
    if not p:
        return ""
    digits = "".join(ch for ch in p if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


def _get_outbound_attempts(start_ms: int, end_ms: int) -> dict[str, list[int]]:
    """phone (нормалізований) → список timestamps усіх ВИХІДНИХ спроб за день
    (успішні 'out' + без відповіді 'no_answer'). Для перевірки "передзвонили чи ні"."""
    attempts: dict[str, list[int]] = defaultdict(list)
    with sqlite3.connect(config.DB_PATH) as c:
        rows = c.execute(
            """SELECT phone, processed_at FROM processed
               WHERE processed_at BETWEEN ? AND ?
                 AND kind IN ('out', 'no_answer')""",
            (start_ms, end_ms),
        ).fetchall()
    for phone, ts in rows:
        p = _norm_phone(phone)
        if p:
            attempts[p].append(ts)
    return attempts


def _callback_status(phone: str | None, after_ts: int, attempts: dict[str, list[int]]) -> str:
    """Чи був вихідний на цей номер ПІСЛЯ вказаного моменту."""
    p = _norm_phone(phone)
    if not p:
        return "немає номера"
    later = [t for t in attempts.get(p, []) if t > after_ts]
    if not later:
        return "НЕ передзвонювали (за даними бота)"
    return f"передзвонювали ({len(later)} раз)"


def _in_call_str(c: dict, callbacks: dict[str, list[int]]) -> str:
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
    # Для ризикових або не записаних — показуємо чи був передзвін
    if c.get("risk", 0) >= 2 or c.get("booked") == 0:
        parts.append(f"  передзвін: {_callback_status(c.get('phone'), c.get('processed_at', 0), callbacks)}")
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


def _write_report(incoming: list[dict], outgoing: list[dict], missed: list[dict],
                  date_str: str, callbacks: dict[str, list[int]]) -> str:
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

    hours = Counter()
    for c in missed:
        dt = datetime.fromtimestamp(c["processed_at"] / 1000, tz=KYIV_TZ)
        hours[dt.hour] += 1
    missed_hours = (
        ", ".join(f"{h:02d}:00→{n}" for h, n in sorted(hours.items())) or "—"
    )
    missed_phones = "\n".join(
        f"— {c.get('phone') or '—'} ({_callback_status(c.get('phone'), c.get('processed_at', 0), callbacks)})"
        for c in missed[:10]
    ) or "—"

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
        in_calls="\n\n".join(_in_call_str(c, callbacks) for c in incoming) or "—",
        out_calls="\n\n".join(_out_call_str(c) for c in outgoing) or "—",
        missed_phones=missed_phones,
    )

    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=16000,
        messages=[{"role": "user", "content": prompt}],
    )
    parts = [b.text for b in msg.content if getattr(b, "type", None) == "text"]
    text = "\n".join(parts).strip()
    if not text:
        return f"(звіт не згенеровано, stop_reason={msg.stop_reason})"
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--yesterday", action="store_true")
    parser.add_argument("--date", help="YYYY-MM-DD")
    args = parser.parse_args()

    now = datetime.now(KYIV_TZ)
    if args.date:
        target = date_cls.fromisoformat(args.date)
    elif args.yesterday:
        target = (now - timedelta(days=1)).date()
    else:
        target = now.date()
    start = datetime.combine(target, time(0, 0), tzinfo=KYIV_TZ)
    end = start + timedelta(days=1)
    if end > now:
        end = now
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)

    calls = db.get_today_calls(start_ms, end_ms)  # dismissed уже исключены
    missed = db.get_today_missed(start_ms, end_ms)
    callbacks = _get_outbound_attempts(start_ms, end_ms)
    date_str = target.strftime("%d.%m.%Y")

    incoming = [c for c in calls if c.get("kind") in ("in", None, "")]
    outgoing = [c for c in calls if c.get("kind") == "out"]

    if not calls and not missed:
        notify.send(f"📊 <b>Підсумки за {date_str}</b>\n\nЗа сьогодні активності не було.")
        return

    header = (
        f"📊 <b>Підсумки за {date_str}</b>  ·  "
        f"📥{len(incoming)}  📤{len(outgoing)}  📞×{len(missed)}\n\n"
    )
    body = _write_report(incoming, outgoing, missed, date_str, callbacks)
    notify.send(header + body)


if __name__ == "__main__":
    main()
