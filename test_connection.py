"""Проверка подключений: Phonet, Anthropic, Telegram.

Запуск: python test_connection.py
"""
import sys
from datetime import datetime

import config
import notify
from phonet import PhonetClient, ms_now


def test_phonet():
    print("[1/3] Phonet API ...", end=" ", flush=True)
    c = PhonetClient()
    now = ms_now()
    calls = c.list_company_calls(now - 24 * 60 * 60 * 1000, now, directions=4, limit=50)
    print(f"OK, за сутки {len(calls)} входящих звонков")
    if calls:
        print(f"      последний: {calls[0].get('otherLegNum')} "
              f"({calls[0].get('billSecs')}s)")


def test_anthropic():
    print("[2/3] Anthropic Claude ...", end=" ", flush=True)
    from anthropic import Anthropic
    cl = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    r = cl.messages.create(
        model="claude-haiku-4-5",
        max_tokens=20,
        messages=[{"role": "user", "content": "ответь одним словом: привет"}],
    )
    print(f"OK ({r.content[0].text.strip()!r})")


def test_telegram():
    print("[3/3] Telegram ...", end=" ", flush=True)
    notify.send(
        f"✅ Тестовое сообщение от бота контроля качества\n"
        f"⏰ {datetime.now():%Y-%m-%d %H:%M:%S}"
    )
    print("OK, проверьте чат")


if __name__ == "__main__":
    try:
        test_phonet()
    except Exception as e:
        print(f"FAIL: {e}")
        sys.exit(1)
    try:
        test_anthropic()
    except Exception as e:
        print(f"FAIL: {e}")
        sys.exit(1)
    try:
        test_telegram()
    except Exception as e:
        print(f"FAIL: {e}")
        sys.exit(1)
    print("\nВсе проверки пройдены.")
