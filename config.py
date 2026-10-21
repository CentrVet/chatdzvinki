import os
from dotenv import load_dotenv

# Используем Windows-ное хранилище сертификатов (нужно если антивирус перехватывает HTTPS)
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

load_dotenv()

PHONET_DOMAIN = os.environ["PHONET_DOMAIN"]
PHONET_API_KEY = os.environ["PHONET_API_KEY"]

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# Защита: сообщения мають йти лише в групу / супергрупу / канал (ID < 0),
# ніколи — в особисте листування. Якщо .env не прочитано і підхопився
# якийсь залишковий user-id з оточення — краще впасти тут, ніж спамити в особисте.
try:
    _chat_id_int = int(TELEGRAM_CHAT_ID)
except ValueError:
    raise RuntimeError(f"TELEGRAM_CHAT_ID має бути числом, отримано: {TELEGRAM_CHAT_ID!r}")
if _chat_id_int >= 0:
    raise RuntimeError(
        f"TELEGRAM_CHAT_ID={TELEGRAM_CHAT_ID} схоже на особистий чат (додатнє число). "
        f"Очікується ID групи або каналу (від'ємне число). "
        f"Перевір .env у D:\\bot і робочий каталог процесу."
    )

MIN_DURATION_SECONDS = int(os.getenv("MIN_DURATION_SECONDS", "20"))
POLL_WINDOW_MINUTES = int(os.getenv("POLL_WINDOW_MINUTES", "15"))
POLL_INTERVAL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", "10"))

# Тихие часы: КЦ не работает, звонки не проверяем (локальное время, час 0-23)
QUIET_HOURS_START = int(os.getenv("QUIET_HOURS_START", "22"))
QUIET_HOURS_END = int(os.getenv("QUIET_HOURS_END", "8"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_CACHE_DIR = os.path.join(BASE_DIR, "audio_cache")
DB_PATH = os.path.join(BASE_DIR, "processed.db")

os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
