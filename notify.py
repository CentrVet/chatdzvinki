import html
import requests
from datetime import datetime, timezone, timedelta

import config
from analyze import CRITERIA


KYIV_TZ = timezone(timedelta(hours=2))  # EET; літом EEST +3, але Phonet віддає UTC


def format_duration(sec) -> str:
    m, s = divmod(int(sec), 60)
    return f"{m}:{s:02d}"


def format_report(call: dict, analysis: dict, audio_url: str, outbound: bool = False) -> str:
    risk = analysis["risk"]
    total = analysis.get("total_score", 0)
    max_score = analysis.get("max_score", 0)
    scores = analysis.get("scores", {})

    if risk >= 3:
        icon = "🔴"
    elif risk == 2:
        icon = "🟠"
    elif risk == 1:
        icon = "🟡"
    else:
        icon = "🟢"

    phone = call.get("otherLegNum") or call.get("otherLegName") or "—"
    duration = format_duration(call.get("billSecs", 0))
    operator = (call.get("leg") or {}).get("displayName", "—")

    end_at_ms = call.get("endAt", 0)
    if end_at_ms:
        dt = datetime.fromtimestamp(end_at_ms / 1000, tz=KYIV_TZ)
        date_str = dt.strftime("%d.%m.%Y")
        time_str = dt.strftime("%H:%M:%S")
    else:
        date_str = time_str = "—"

    lang_map = {"uk": "🇺🇦 Українська", "ru": "🇷🇺 Російська", "mix": "🌐 Змішана"}
    lang = lang_map.get(analysis.get("language", "uk"), "—")

    direction_tag = "📤 ВИХІДНИЙ" if outbound else "📥 ВХІДНИЙ"

    if outbound:
        header = f"{icon} <b>{direction_tag}  |  Ризик: {risk}/3</b>"
    else:
        header = f"{icon} <b>{direction_tag}  |  Бал: {total}/{max_score}  |  Ризик: {risk}/3</b>"

    lines = [
        header,
        "",
        f"📞 <code>{html.escape(phone)}</code>",
        f"📅 {date_str}  🕐 {time_str}  ⏱ {duration} хв",
        f"👤 Оператор: {html.escape(operator)}",
        f"{lang}",
    ]

    if not outbound:
        booked = analysis.get("booked")
        if booked is True:
            booked_str = "📝 Записався"
        elif booked is False:
            booked_str = "🚶 НЕ записався"
        else:
            booked_str = "❓ Запис нечітко"
        lines[-1] = f"{lang}  |  {booked_str}"

    lines.append("")
    lines.append(f"📋 {html.escape(analysis['summary'])}")

    if not outbound:
        upsell = analysis.get("missed_upsell")
        if upsell:
            lines.append("")
            lines.append(f"💰 <b>Упущено:</b> {html.escape(upsell)}")

        def mark(val: int) -> str:
            if val >= 2:
                return "✅ 2/2"
            if val == 1:
                return "⚠️ 1/2"
            return "❌ 0/2"

        lines.append("")
        lines.append("<b>Чекліст:</b>")
        for key, desc in CRITERIA:
            lines.append(f"{mark(scores.get(key, 0))} {html.escape(desc)}")

    if risk > 0:
        lines.append("")
        lines.append(f"❗ <b>Чому ризик {risk}:</b> {html.escape(analysis['reason'])}")
        lines.append(f"✅ <b>Що робити:</b> {html.escape(analysis['fix'])}")

    lines.append("")
    lines.append(f'🎧 <a href="{audio_url}">Прослухати запис</a>')
    return "\n".join(lines)


TG_LIMIT = 4000  # запас от 4096


def _split(text: str) -> list[str]:
    """Делит длинный текст по границам абзацев/строк, не ломая HTML-теги в середине."""
    if len(text) <= TG_LIMIT:
        return [text]
    parts = []
    rest = text
    while len(rest) > TG_LIMIT:
        cut = rest.rfind("\n\n", 0, TG_LIMIT)
        if cut < TG_LIMIT // 2:
            cut = rest.rfind("\n", 0, TG_LIMIT)
        if cut < TG_LIMIT // 2:
            cut = TG_LIMIT
        parts.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        parts.append(rest)
    return parts


def send(text: str) -> None:
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    for part in _split(text):
        r = requests.post(
            url,
            json={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": part,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        r.raise_for_status()
