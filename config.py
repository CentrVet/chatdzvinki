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
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

MIN_DURATION_SECONDS = int(os.getenv("MIN_DURATION_SECONDS", "20"))
POLL_WINDOW_MINUTES = int(os.getenv("POLL_WINDOW_MINUTES", "15"))
POLL_INTERVAL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", "10"))
DIRECTIONS = int(os.getenv("DIRECTIONS", "4"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_CACHE_DIR = os.path.join(BASE_DIR, "audio_cache")
DB_PATH = os.path.join(BASE_DIR, "processed.db")

os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
