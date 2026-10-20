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
from datetime import datetime

import config
import db
import notify
from phonet import PhonetClient, ms_now
from transcribe import transcribe
from analyze import analyze, analyze_outbound


# Phonet direction codes (based on project config): 4 = incoming, 2 = outgoing
INCOMING = 4
OUTGOING = 2


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("qc")


def _mark_skip(uuid: str, call: dict, kind: str) -> None:
    db.mark_processed(
        uuid, ms_now(), -1, -1,
        call.get("otherLegNum") or "",
        (call.get("leg") or {}).get("displayName", ""),
        kind=kind,
    )


def process_call(client: PhonetClient, call: dict) -> None:
    uuid = call["uuid"]

    if db.is_processed(uuid):
        return

    # Phonet возвращает направление в поле lgDirection (поле direction = null)
    direction = call.get("lgDirection") or call.get("direction")
    bill_secs = call.get("billSecs", 0) or 0
    audio_url = call.get("audioRecUrl")

    # Пропущенный входящий — считаем в статистике, не анализируем
    if direction == INCOMING and (bill_secs == 0 or not audio_url):
        log.info("missed incoming %s (bill=%ss)", uuid, bill_secs)
        _mark_skip(uuid, call, "missed")
        return

    # Исходящий без ответа — пропускаем
    if direction == OUTGOING and (bill_secs == 0 or not audio_url):
        log.info("outgoing no-answer %s (bill=%ss)", uuid, bill_secs)
        _mark_skip(uuid, call, "no_answer")
        return

    if bill_secs < config.MIN_DURATION_SECONDS:
        log.info("skip %s: too short (%ss)", uuid, bill_secs)
        _mark_skip(uuid, call, "short")
        return

    if not audio_url:
        log.info("skip %s: no audioRecUrl", uuid)
        _mark_skip(uuid, call, "no_audio")
        return

    audio_path = os.path.join(config.AUDIO_CACHE_DIR, f"{uuid}.mp3")
    log.info("download %s dir=%s (%ss)", uuid, direction, bill_secs)
    if client.download_audio(uuid, audio_path) is None:
        log.info("skip %s: no audio file on server", uuid)
        _mark_skip(uuid, call, "no_audio")
        return

    log.info("transcribe %s", uuid)
    transcript = transcribe(audio_path)
    if len(transcript) < 20:
        log.info("skip %s: empty transcript", uuid)
        _mark_skip(uuid, call, "short")
        try:
            os.remove(audio_path)
        except OSError:
            pass
        return

    is_outbound = direction == OUTGOING
    log.info("analyze %s (%s)", uuid, "OUT" if is_outbound else "IN")
    analysis = analyze_outbound(transcript) if is_outbound else analyze(transcript)

    if analysis.get("is_supplier"):
        log.info("supplier/B2B call %s, skipping: %s", uuid, analysis.get("reason", ""))
        _mark_skip(uuid, call, "supplier")
        try:
            os.remove(audio_path)
        except OSError:
            pass
        return

    kind = "out" if is_outbound else "in"

    log.info(
        "analyzed %s %s risk=%s score=%s/%s",
        uuid, kind, analysis["risk"], analysis["total_score"], analysis["max_score"],
    )

    # Фильтр: в Telegram только риск >= 2 (клиент недоволен/не записался/жалоба)
    if analysis["risk"] >= 2:
        notify.send(notify.format_report(call, analysis, audio_url, outbound=is_outbound))
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
        kind=kind,
    )

    try:
        os.remove(audio_path)
    except OSError:
        pass


def is_quiet_hours(now: datetime | None = None) -> bool:
    now = now or datetime.now()
    start = config.QUIET_HOURS_START
    end = config.QUIET_HOURS_END
    h = now.hour
    if start == end:
        return False
    if start < end:
        return start <= h < end
    return h >= start or h < end


def run_once() -> None:
    if is_quiet_hours():
        log.info(
            "quiet hours (%02d:00-%02d:00), skip",
            config.QUIET_HOURS_START, config.QUIET_HOURS_END,
        )
        return
    client = PhonetClient()
    now = ms_now()
    time_from = now - config.POLL_WINDOW_MINUTES * 60 * 1000
    log.info("poll window: last %s min, all directions", config.POLL_WINDOW_MINUTES)
    calls = client.list_company_calls(
        time_from_ms=time_from,
        time_to_ms=now,
        directions=None,  # все направления: входящие + исходящие + пропущенные
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
