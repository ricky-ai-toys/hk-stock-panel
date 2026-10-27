"""CCASS history window: allowed ranges, coverage, and one-at-a-time backfill.

HKEX CCASS search only serves roughly the last 12 months, so every lookback is
capped at 365 calendar days. Longer UI windows (180 / 365 trading sessions)
reuse the existing rate-limited scraper and never run two crawls for the same
stock at once.
"""
import math
import threading
import time
from datetime import datetime, timedelta

# Trading-session choices shown in the CCASS tab. 365 is the ceiling.
CCASS_RANGE_OPTIONS = (30, 60, 90, 180, 365)
CCASS_RANGE_DEFAULT = 60
HKEX_CCASS_MAX_CALENDAR_DAYS = 365
# A finished automatic backfill that still looks short is not retried immediately.
BACKFILL_RETRY_COOLDOWN_S = 600
# How many query dates to fetch and save before starting the next group.
BACKFILL_BATCH_SIZE = 8

_guard = threading.Lock()
_runs: dict[str, dict] = {}


def calendar_lookback_days(trading_days: int) -> int:
    """Calendar span that should cover `trading_days` sessions, never past 12 months.

    The historical backfill used `days * 1.6` to turn a trading-day count into
    calendar days (weekends). That expansion is kept, then capped so a 365-day
    request does not walk ~584 calendar days of dates HKEX will not return.
    """
    trading_days = max(1, int(trading_days))
    return min(HKEX_CCASS_MAX_CALENDAR_DAYS, int(trading_days * 1.6))


def chunked(items, size: int):
    step = max(1, int(size))
    for i in range(0, len(items), step):
        yield items[i:i + step]


def plan_backfill_query_dates(existing_data_dates, end_query: datetime, trading_days: int, to_data_date) -> list[str]:
    """Weekday query dates (YYYY/MM/DD) inside the capped window, skipping stored sessions.

    `to_data_date` maps a query date to the CCASS trade date stored in the DB
    (HKEX publishes on a T-2 working-day lag).
    """
    lookback = calendar_lookback_days(trading_days)
    floor = end_query - timedelta(days=HKEX_CCASS_MAX_CALENDAR_DAYS)
    start = end_query - timedelta(days=lookback)
    if start < floor:
        start = floor

    planned = []
    cur = start
    existing = set(existing_data_dates or ())
    while cur <= end_query:
        if cur.weekday() < 5:
            query_date = cur.strftime('%Y/%m/%d')
            if to_data_date(query_date) not in existing:
                planned.append(query_date)
        cur += timedelta(days=1)
    return planned


def assess_ccass_coverage(trade_dates, requested_days: int, today: datetime | None = None) -> dict:
    """Decide whether the DB already spans the requested trading-day window.

    Sufficient when any of these is true:
    - at least `requested_days` sessions are stored
    - the earliest session already reaches the calendar span of that window
      (holiday gaps inside a finished walk are not treated as a reason to scrape again)
    - the earliest session reaches the 12-month HKEX floor, so older rows do not exist
    """
    requested = max(1, min(HKEX_CCASS_MAX_CALENDAR_DAYS, int(requested_days)))
    dates = sorted({d for d in (trade_dates or []) if d})
    available = len(dates)
    earliest = dates[0] if dates else None
    latest = dates[-1] if dates else None
    if latest:
        ref = datetime.strptime(latest, '%Y-%m-%d')
    elif today is not None:
        ref = today
    else:
        ref = datetime.utcnow()

    lookback = calendar_lookback_days(requested)
    needed = ref - timedelta(days=lookback)
    hkex_floor = ref - timedelta(days=HKEX_CCASS_MAX_CALENDAR_DAYS)
    # Weekend alignment can leave the first stored session a couple of days
    # inside the nominal start. Don't treat that as a missing year of history.
    slack = timedelta(days=4)

    def _on_or_before(stored: str | None, boundary: datetime) -> bool:
        if not stored:
            return False
        return datetime.strptime(stored, '%Y-%m-%d') <= boundary + slack

    spans_request = _on_or_before(earliest, needed)
    reaches_hkex_floor = _on_or_before(earliest, hkex_floor)
    sufficient = available >= requested or spans_request or reaches_hkex_floor
    return {
        'requested_days': requested,
        'available_days': available,
        'earliest': earliest,
        'latest': latest,
        'sufficient': bool(sufficient),
        'hkex_capped': bool(reaches_hkex_floor and available < requested),
    }


def ccass_ensure_progress_pct(done: int, total: int) -> int:
    """Percent for an on-demand history fill.

    A long window has hundreds of dates, so truncating `done / total` makes the
    first steps display as 0%. Once any date has finished, the value is at least
    1 and at most 99 until the job is marked complete.
    """
    if done <= 0 or total <= 0:
        return 0
    pct = math.ceil((done * 100) / total)
    return min(99, max(1, int(pct)))


def claim_ccass_backfill(code: str, days: int, job_id: str) -> tuple[bool, dict]:
    """Reserve the single CCASS crawl for this stock.

    Returns (is_leader, state). A follower just raises `target_days` on the
    crawl that is already running and is added to `job_ids`, so every waiter
    can show the same progress. The leader picks the higher target up after
    the current pass instead of opening a second connection to HKEX.
    """
    days = max(1, min(HKEX_CCASS_MAX_CALENDAR_DAYS, int(days)))
    code = code.zfill(5)
    with _guard:
        state = _runs.get(code)
        if state and state['status'] == 'running':
            state['target_days'] = max(state['target_days'], days)
            _remember_job_id(state, job_id)
            return False, state
        state = {
            'job_id': job_id,
            'job_ids': [job_id],
            'target_days': days,
            'status': 'running',
            'error': None,
            'fetched': 0,
            'finished_at': None,
            'done': threading.Event(),
        }
        _runs[code] = state
        return True, state


def _remember_job_id(state: dict, job_id: str) -> None:
    """Caller must hold `_guard`."""
    jobs = state.setdefault('job_ids', [])
    if job_id not in jobs:
        jobs.append(job_id)


def ccass_backfill_job_ids(state: dict) -> list[str]:
    with _guard:
        return list(state.get('job_ids') or ())


def record_ccass_progress(state: dict, pct: int, date: str | None) -> list[str]:
    """Remember the crawl's latest percent and return every job that should show it."""
    with _guard:
        state['progress'] = int(pct)
        if date:
            state['current_date'] = date
        return list(state.get('job_ids') or ())


def shared_ccass_progress(state: dict) -> tuple[int | None, str | None]:
    """Latest percent published for this crawl, or `(None, None)` before the first date."""
    with _guard:
        if 'progress' not in state:
            return None, None
        return state.get('progress'), state.get('current_date')


def get_ccass_backfill_state(code: str) -> dict | None:
    code = code.zfill(5)
    with _guard:
        state = _runs.get(code)
        if not state:
            return None
        return {
            'job_id': state['job_id'],
            'target_days': state['target_days'],
            'status': state['status'],
            'error': state.get('error'),
            'fetched': state.get('fetched') or 0,
            'finished_at': state.get('finished_at'),
        }


def should_skip_automatic_backfill(code: str, days: int, now: float | None = None) -> dict | None:
    """Return the recent attempt when another automatic crawl would only repeat it.

    Manual "update data" does not call this. It only stops the CCASS tab from
    re-queueing the same window on every refresh / tab switch.
    """
    state = get_ccass_backfill_state(code)
    if not state or state['target_days'] < days:
        return None
    if state['status'] == 'running':
        return state
    if state['status'] not in ('done', 'error'):
        return None
    finished = state.get('finished_at')
    if finished is None:
        return state
    elapsed = (now if now is not None else time.time()) - finished
    if elapsed < BACKFILL_RETRY_COOLDOWN_S:
        return state
    return None


def run_ccass_backfill_leader(code: str, state: dict, progress_callback=None, runner=None) -> int:
    """Run the leader pass. Blocks. Expands the window if `target_days` grows mid-run."""
    if runner is None:
        from scrapers.ccass_scraper import backfill_stock
        runner = backfill_stock

    total_fetched = 0
    try:
        while True:
            with _guard:
                target = state['target_days']
            fetched = runner(code, days=target, progress_callback=progress_callback, max_workers=2) or 0
            total_fetched += int(fetched)
            with _guard:
                state['fetched'] = total_fetched
                if state['target_days'] <= target:
                    state['status'] = 'done'
                    state['error'] = None
                    return total_fetched
    except Exception as e:
        with _guard:
            state['status'] = 'error'
            state['error'] = str(e)
            state['fetched'] = total_fetched
        raise
    finally:
        with _guard:
            if state['status'] == 'running':
                state['status'] = 'error'
                state['error'] = state.get('error') or 'backfill interrupted'
            state['finished_at'] = time.time()
        state['done'].set()


def reset_ccass_backfill_state():
    """Test helper. Does not touch in-flight threads."""
    with _guard:
        _runs.clear()
