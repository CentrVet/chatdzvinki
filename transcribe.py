"""Расшифровка через Groq Whisper API.

Быстро, дёшево, не требует GPU — подходит для запуска в GitHub Actions / VPS.
"""
import os
import requests

import config


GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MODEL = "whisper-large-v3-turbo"  # быстрый и точный


def transcribe(audio_path: str, language: str | None = None) -> str:
    """Расшифровывает аудиофайл через Groq API.

    language: "uk" / "ru" / None (автоопределение).
    """
    with open(audio_path, "rb") as f:
        files = {"file": (os.path.basename(audio_path), f, "audio/mpeg")}
        data = {"model": MODEL, "response_format": "text"}
        if language:
            data["language"] = language
        headers = {"Authorization": f"Bearer {config.GROQ_API_KEY}"}
        r = requests.post(GROQ_URL, headers=headers, files=files, data=data, timeout=120)
    r.raise_for_status()
    return r.text.strip()
