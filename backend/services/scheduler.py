"""
Lightweight daily auto-fetch scheduler.
Uses a single daemon thread; no external dependencies.
Reads auto_fetch config (enabled, time "HH:MM", days) and triggers a
background fetch for all monitored stocks once per day.
"""
import logging
import threading
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_scheduler_thread: threading.Thread | None = None
_stop_event = threading.Event()
_last_run_date: str | None = None
_lock = threading.Lock()


def _parse_hhmm(s: str) -> tuple[int, int]:
    try:
        parts = (s or "17:30").split(":")
        return int(parts[0]), int(parts[1])
    except Exception:
        return 17, 30


def _seconds_until_next(hour: int, minute: int) -> float:
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _run_fetch_for_all_stocks(days: int):
    """Trigger a background fetch job for every monitored stock."""
    import importlib
    from db import list_stocks
    # Lazy-import app so this module can be imported during app startup
    app_module = importlib.import_module('app')
    stocks = list_stocks()
    for s in stocks:
        code = (s.get('stock_code') or '').zfill(5)
        if not code or code == '00000':
            continue
        try:
            job_id = __import__('uuid').uuid4().hex[:12]
            t = threading.Thread(
                target=app_module._run_fetch_job,
                args=(job_id, code, days),
                daemon=True,
            )
            t.start()
            logger.info(f"[AutoFetch] Scheduled job {job_id} for {code} (days={days})")
            # Small stagger to avoid slamming upstream sources all at once
            time.sleep(8)
        except Exception as e:
            logger.error(f"[AutoFetch] Failed to schedule {code}: {e}")


def _scheduler_loop():
    global _last_run_date
    logger.info("[AutoFetch] Scheduler thread started")
    while not _stop_event.is_set():
        try:
            from services.config_service import load_config
            cfg = load_config().get('auto_fetch', {})
            enabled = bool(cfg.get('enabled'))
            hour, minute = _parse_hhmm(cfg.get('time'))
            days = int(cfg.get('days') or 90)

            if not enabled:
                # Sleep 60s and re-check config (so enabling it takes effect without restart)
                _stop_event.wait(60)
                continue

            wait_s = _seconds_until_next(hour, minute)
            logger.info(f"[AutoFetch] Next run at {hour:02d}:{minute:02d} (in {int(wait_s/60)} min)")

            # Wait in short increments so config changes / stop are responsive
            waited = 0.0
            while waited < wait_s and not _stop_event.is_set():
                chunk = min(30.0, wait_s - waited)
                _stop_event.wait(chunk)
                waited += chunk
                # Re-check config in case user changed the time while waiting
                try:
                    cfg2 = load_config().get('auto_fetch', {})
                    if not cfg2.get('enabled'):
                        break
                    h2, m2 = _parse_hhmm(cfg2.get('time'))
                    if (h2, m2) != (hour, minute):
                        hour, minute = h2, m2
                        break  # recompute wait
                except Exception:
                    pass

            if _stop_event.is_set():
                break

            today = datetime.now().strftime('%Y-%m-%d')
            with _lock:
                already_ran = _last_run_date == today
            if enabled and not already_ran:
                logger.info(f"[AutoFetch] Running daily fetch for all stocks (days={days})")
                try:
                    _run_fetch_for_all_stocks(days)
                    with _lock:
                        _last_run_date = today
                except Exception as e:
                    logger.error(f"[AutoFetch] Run failed: {e}")

            # Don't run again for at least 30 min (avoid tight loops if schedule mis-set)
            _stop_event.wait(1800)
        except Exception as e:
            logger.error(f"[AutoFetch] Loop error: {e}")
            _stop_event.wait(60)


def start():
    """Start the scheduler daemon thread (idempotent)."""
    global _scheduler_thread, _stop_event
    if _scheduler_thread and _scheduler_thread.is_alive():
        return
    _stop_event.clear()
    _scheduler_thread = threading.Thread(target=_scheduler_loop, name="auto-fetch-scheduler", daemon=True)
    _scheduler_thread.start()


def stop():
    global _scheduler_thread
    _stop_event.set()
    _scheduler_thread = None


def status() -> dict:
    """Return current scheduler status for the UI/API."""
    from services.config_service import load_config
    cfg = load_config().get('auto_fetch', {})
    hour, minute = _parse_hhmm(cfg.get('time'))
    enabled = bool(cfg.get('enabled'))
    next_run_in_s = _seconds_until_next(hour, minute) if enabled else None
    return {
        'enabled': enabled,
        'time': cfg.get('time') or '17:30',
        'days': int(cfg.get('days') or 90),
        'last_run_date': _last_run_date,
        'next_run_in_minutes': round(next_run_in_s / 60) if next_run_in_s is not None else None,
        'running': bool(_scheduler_thread and _scheduler_thread.is_alive()),
    }


def trigger_now() -> dict:
    """Immediately trigger a fetch for all stocks (manual run from UI)."""
    from services.config_service import load_config
    cfg = load_config().get('auto_fetch', {})
    days = int(cfg.get('days') or 90)

    def _bg():
        logger.info("[AutoFetch] Manual trigger requested")
        _run_fetch_for_all_stocks(days)
        global _last_run_date
        with _lock:
            _last_run_date = datetime.now().strftime('%Y-%m-%d')
    t = threading.Thread(target=_bg, daemon=True)
    t.start()
    return {'status': 'started', 'days': days}
