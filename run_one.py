"""Разовый прогон — обработать ровно один звонок (первый подходящий за N часов)
и прислать отчёт. Для тестов.

Запуск: python run_one.py
"""
import logging
import os
import sys

import config
import db
import notify
from phonet import PhonetClient, ms_now
from transcribe import transcribe
from analyze import analyze


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("one")


def main():
    hours_back = 24
    client = PhonetClient()
    now = ms_now()
    calls = client.list_company_calls(
        time_from_ms=now - hours_back * 60 * 60 * 1000,
        time_to_ms=now,
        directions=4,
    )
    log.info("found %d calls in last %dh", len(calls), hours_back)

    # Пробуем звонки по очереди пока не найдём с реально работающей записью
    picked = None
    audio_path = None
    for call in calls:
        if (call.get("billSecs", 0) or 0) < 30:
            continue
        if not call.get("audioRecUrl"):
            continue
        if db.is_processed(call["uuid"]):
            continue
        uuid = call["uuid"]
        candidate_path = os.path.join(config.AUDIO_CACHE_DIR, f"{uuid}.mp3")
        log.info("try %s (%ss)...", uuid, call.get("billSecs"))
        if client.download_audio(uuid, candidate_path) is None:
            log.info("  no audio file, next")
            continue
        picked = call
        audio_path = candidate_path
        break

    if not picked:
        log.warning("no suitable call with audio found")
        sys.exit(1)

    uuid = picked["uuid"]
    log.info("downloaded %s", uuid)

    log.info("transcribing...")
    transcript = transcribe(audio_path)
    log.info("transcript (%d chars): %s", len(transcript), transcript[:200])

    if len(transcript) < 20:
        log.error("empty transcript")
        sys.exit(1)

    log.info("analyzing...")
    analysis = analyze(transcript)
    log.info("risk=%d score=%d/%d", analysis["risk"], analysis["total_score"], analysis["max_score"])

    log.info("sending to telegram...")
    notify.send(notify.format_report(picked, analysis, picked["audioRecUrl"]))
    db.mark_processed(
        uuid, ms_now(), analysis["risk"], analysis["total_score"],
        picked.get("otherLegNum") or "",
        (picked.get("leg") or {}).get("displayName", ""),
    )
    try:
        os.remove(audio_path)
    except OSError:
        pass
    log.info("done")


if __name__ == "__main__":
    main()
