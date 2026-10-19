"""Основной цикл. Запуск: python main.py

Можно запускать:
  - через Windows Task Scheduler раз в POLL_INTERVAL_MINUTES минут (одна итерация → выход)
  - или postoянно: python main.py --loop
"""
import argparse
import logging
import os
import sys
import time
import traceback

import config
import db
import notify
from phonet import PhonetClient, ms_now
from transcribe import transcribe
from analyze import analyze


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("qc")


def process_call(client: PhonetClient, call: dict) -> None:
    uuid = call["uuid"]

    if db.is_processed(uuid):
        return

    bill_secs = call.get("billSecs", 0) or 0
    if bill_secs < config.MIN_DURATION_SECONDS:
        log.info("skip %s: too short (%ss)", uuid, bill_secs)
        db.mark_processed(uuid, ms_now(), -1, -1, call.get("otherLegNum") or "", "")
        return

    audio_url = call.get("audioRecUrl")
    if not audio_url:
        log.info("skip %s: no audioRecUrl", uuid)
        db.mark_processed(uuid, ms_now(), -1, -1, call.get("otherLegNum") or "", "")
        return

    audio_path = os.path.join(config.AUDIO_CACHE_DIR, f"{uuid}.mp3")
    log.info("download %s (%ss)", uuid, bill_secs)
    if client.download_audio(uuid, audio_path) is None:
        log.info("skip %s: no audio file on server", uuid)
        db.mark_processed(uuid, ms_now(), -1, -1, call.get("otherLegNum") or "", "")
        return

    log.info("transcribe %s", uuid)
    transcript = transcribe(audio_path)
    if len(transcript) < 20:
        log.info("skip %s: empty transcript", uuid)
        db.mark_processed(uuid, ms_now(), -1, -1, call.get("otherLegNum") or "", "")
        try:
            os.remove(audio_path)
        except OSError:
            pass
        return

    log.info("analyze %s", uuid)
    analysis = analyze(transcript)

    log.info(
        "analyzed %s risk=%s score=%s/%s",
        uuid, analysis["risk"], analysis["total_score"], analysis["max_score"],
    )

    # Фильтр: в Telegram только риск >= 2 (клиент недоволен/не записался/жалоба)
    # Риск 0 (ок) и 1 (мелкие недочёты) идут только в дневной отчёт
    if analysis["risk"] >= 2:
        notify.send(notify.format_report(call, analysis, audio_url))
        log.info("sent to telegram (risk=%d)", analysis["risk"])
    else:
        log.info("risk=%d, only daily report", analysis["risk"])

    db.mark_processed(
        uuid,
        ms_now(),
        analysis["risk"],
        analysis["total_score"],
        call.get("otherLegNum") or "",
        (call.get("leg") or {}).get("displayName", ""),
        max_score=analysis["max_score"],
        summary=analysis.get("summary", ""),
        reason=analysis.get("reason", ""),
        booked=analysis.get("booked"),
        missed_upsell=analysis.get("missed_upsell"),
    )

    # кэш не копим, после отправки чистим
    try:
        os.remove(audio_path)
    except OSError:
        pass


def run_once() -> None:
    client = PhonetClient()
    now = ms_now()
    time_from = now - config.POLL_WINDOW_MINUTES * 60 * 1000
    log.info(
        "poll window: last %s min, directions=%s",
        config.POLL_WINDOW_MINUTES,
        config.DIRECTIONS,
    )
    calls = client.list_company_calls(
        time_from_ms=time_from,
        time_to_ms=now,
        directions=config.DIRECTIONS,
    )
    log.info("got %s calls", len(calls))
    for call in calls:
        try:
            process_call(client, call)
        except Exception:
            log.error("failed on %s:\n%s", call.get("uuid"), traceback.format_exc())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true", help="бесконечный цикл с интервалом")
    args = parser.parse_args()

    if not args.loop:
        run_once()
        return

    interval = config.POLL_INTERVAL_MINUTES * 60
    while True:
        try:
            run_once()
        except Exception:
            log.error("iteration failed:\n%s", traceback.format_exc())
        log.info("sleep %s sec", interval)
        time.sleep(interval)


if __name__ == "__main__":
    main()
