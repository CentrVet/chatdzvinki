"""Обработка ответов в Telegram.

Единственная функция: пользователь отвечает на алерт в Telegram с коротким
комментарием → звонок помечается как dismissed (не проблема) с причиной.
Исключается из будущих отчётов.

Запускается в начале каждого цикла poll.yml.
"""
import re
import traceback
from pathlib import Path

import requests

import config
import db
import notify


OFFSET_FILE = Path(__file__).parent / "tg_offset.txt"
ID_RE = re.compile(r"#id:([0-9a-f]{32})", re.IGNORECASE)


def _get_offset() -> int:
    try:
        return int(OFFSET_FILE.read_text().strip())
    except Exception:
        return 0


def _save_offset(offset: int) -> None:
    OFFSET_FILE.write_text(str(offset))


def _get_updates(offset: int) -> list:
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates"
    r = requests.get(
        url,
        params={"offset": offset, "timeout": 0, "limit": 50, "allowed_updates": '["message"]'},
        timeout=15,
    )
    r.raise_for_status()
    return r.json().get("result", [])


def process_commands() -> None:
    offset = _get_offset()
    updates = _get_updates(offset)
    if not updates:
        return
    for upd in updates:
        _save_offset(upd["update_id"] + 1)
        msg = upd.get("message") or {}
        chat_id = str((msg.get("chat") or {}).get("id") or "")
        if chat_id != str(config.TELEGRAM_CHAT_ID):
            continue

        reply_to = msg.get("reply_to_message")
        if not reply_to:
            continue
        orig_text = reply_to.get("text") or ""
        m = ID_RE.search(orig_text)
        if not m:
            continue
        uuid = m.group(1).lower()
        reason = (msg.get("text") or "").strip()
        if not reason:
            continue

        try:
            db.set_dismissed(uuid, reason)
            notify.send(f"✅ Звонок помічено як 'не проблема'.\nПричина: {reason}")
        except Exception:
            tb = traceback.format_exc()
            notify.send(f"❌ Помилка:\n<pre>{tb[-500:]}</pre>")


if __name__ == "__main__":
    process_commands()
