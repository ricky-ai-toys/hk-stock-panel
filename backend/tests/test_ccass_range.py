"""CCASS day-range coverage, 12-month cap, batched backfill, and the ensure API.

These tests never call HKEX. Network fetches are replaced with local fakes.
"""
import os
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.ccass_range import (  # noqa: E402
    CCASS_RANGE_DEFAULT,
    CCASS_RANGE_OPTIONS,
    assess_ccass_coverage,
    calendar_lookback_days,
    claim_ccass_backfill,
    plan_backfill_query_dates,
    reset_ccass_backfill_state,
    run_ccass_backfill_leader,
)
from scrapers.ccass_scraper import compute_query_to_data_date  # noqa: E402


def _weekdays_ending(n: int, end: datetime) -> list[str]:
    out = []
    cursor = end
    while len(out) < n:
        if cursor.weekday() < 5:
            out.append(cursor.strftime('%Y-%m-%d'))
        cursor -= timedelta(days=1)
    return out


class CcassRangeMathTests(unittest.TestCase):
    def test_options_and_default(self):
        self.assertEqual(CCASS_RANGE_OPTIONS, (30, 60, 90, 180, 365))
        self.assertEqual(CCASS_RANGE_DEFAULT, 60)

    def test_lookback_keeps_short_windows_and_caps_a_year(self):
        self.assertEqual(calendar_lookback_days(90), int(90 * 1.6))
        self.assertEqual(calendar_lookback_days(180), int(180 * 1.6))
        self.assertEqual(calendar_lookback_days(365), 365)
        self.assertEqual(calendar_lookback_days(1000), 365)

    def test_coverage_matches_the_ui_windows(self):
        end = datetime(2026, 10, 23)
        stored_90 = _weekdays_ending(90, end)
        self.assertTrue(assess_ccass_coverage(stored_90, 30)['sufficient'])
        self.assertTrue(assess_ccass_coverage(stored_90, 60)['sufficient'])
        self.assertTrue(assess_ccass_coverage(stored_90, 90)['sufficient'])
        longer = assess_ccass_coverage(stored_90, 180)
        self.assertFalse(longer['sufficient'])
        self.assertEqual(longer['available_days'], 90)
        year = assess_ccass_coverage(stored_90, 365)
        self.assertFalse(year['sufficient'])
        self.assertFalse(year['hkex_capped'])

    def test_twelve_month_floor_is_enough_even_without_365_sessions(self):
        latest = datetime(2026, 10, 23)
        earliest = latest - timedelta(days=365)
        coverage = assess_ccass_coverage(
            [earliest.strftime('%Y-%m-%d'), latest.strftime('%Y-%m-%d')],
            365,
        )
        self.assertTrue(coverage['sufficient'])
        self.assertTrue(coverage['hkex_capped'])

    def test_empty_history_is_not_sufficient(self):
        coverage = assess_ccass_coverage([], 60, today=datetime(2026, 10, 23))
        self.assertFalse(coverage['sufficient'])
        self.assertEqual(coverage['available_days'], 0)

    def test_plan_stays_inside_twelve_months_and_skips_stored_dates(self):
        end = datetime(2026, 10, 23)
        self.assertEqual(end.weekday(), 4)  # Friday, so the window includes the end date
        year = plan_backfill_query_dates(set(), end, 365, compute_query_to_data_date)
        first = datetime.strptime(year[0], '%Y/%m/%d')
        self.assertLessEqual((end - first).days, 365)
        self.assertGreaterEqual((end - first).days, 362)
        # Uncapped 365 * 1.6 calendar days would be ~400 weekday queries.
        self.assertLess(len(year), 280)
        self.assertGreater(len(year), 240)

        quarter = plan_backfill_query_dates(set(), end, 90, compute_query_to_data_date)
        quarter_first = datetime.strptime(quarter[0], '%Y/%m/%d')
        self.assertGreaterEqual((end - quarter_first).days, 140)
        self.assertLessEqual((end - quarter_first).days, 144)

        sample = year[10]
        skipped = plan_backfill_query_dates(
            {compute_query_to_data_date(sample)}, end, 365, compute_query_to_data_date,
        )
        self.assertNotIn(sample, skipped)
        self.assertEqual(len(skipped), len(year) - 1)


class CcassBackfillCoordinatorTests(unittest.TestCase):
    def setUp(self):
        reset_ccass_backfill_state()

    def tearDown(self):
        reset_ccass_backfill_state()

    def test_second_request_extends_the_running_crawl_instead_of_overlapping(self):
        order = []
        gate = threading.Event()

        def runner(code, days=90, progress_callback=None, max_workers=2, **kwargs):
            self.assertEqual(max_workers, 2)
            order.append(('start', days))
            self.assertTrue(gate.wait(2), 'follower did not arrive during the first pass')
            order.append(('end', days))
            return 1

        leader, state = claim_ccass_backfill('00991', 90, 'job-a')
        self.assertTrue(leader)
        worker = threading.Thread(
            target=run_ccass_backfill_leader,
            args=('00991', state),
            kwargs={'runner': runner},
        )
        worker.start()
        deadline = time.time() + 2
        while not order and time.time() < deadline:
            time.sleep(0.01)
        follower, joined = claim_ccass_backfill('00991', 365, 'job-b')
        gate.set()
        self.assertFalse(follower)
        self.assertEqual(joined['job_id'], 'job-a')
        self.assertEqual(joined['target_days'], 365)
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(order, [('start', 90), ('end', 90), ('start', 365), ('end', 365)])
        self.assertEqual(state['status'], 'done')


class CcassBackfillBatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        import db
        self._db = db
        self._orig = (db.DATA_DIR, db.META_DB_PATH, db.UPLOAD_DIR)
        db.DATA_DIR = self.tmp.name
        db.META_DB_PATH = os.path.join(self.tmp.name, '_meta.db')
        db.UPLOAD_DIR = os.path.join(self.tmp.name, 'uploads')
        reset_ccass_backfill_state()

    def tearDown(self):
        self._db.DATA_DIR, self._db.META_DB_PATH, self._db.UPLOAD_DIR = self._orig
        self.tmp.cleanup()
        reset_ccass_backfill_state()

    def test_batches_are_saved_before_the_next_group_is_fetched(self):
        from db import get_stock_conn
        from scrapers.ccass_scraper import backfill_stock, find_latest_query_date

        observed = []
        queried = []
        lock = threading.Lock()
        end = datetime.strptime(find_latest_query_date(), '%Y/%m/%d')

        def fake_fetch(args):
            code, query_date = args
            queried.append(query_date)
            self.assertLessEqual((end - datetime.strptime(query_date, '%Y/%m/%d')).days, 365)
            with get_stock_conn(code) as conn:
                stored = conn.execute(
                    "SELECT COUNT(DISTINCT trade_date) AS n FROM ccass_participants"
                ).fetchone()['n']
            with lock:
                observed.append(stored)
            data_date = compute_query_to_data_date(query_date)
            return data_date, [{
                'participant_id': 'B00001',
                'participant_name': 'Example Broker',
                'shares': 1000,
                'pct_of_issued': 1.5,
            }], {'total_shares': 8000, 'total_pct': 12.0, 'participant_count': 1}

        with patch('scrapers.ccass_scraper._fetch_one_day', side_effect=fake_fetch):
            saved = backfill_stock('00992', days=30, batch_size=3, max_workers=2)

        self.assertGreaterEqual(len(observed), 4)
        self.assertGreater(saved, 0)
        self.assertTrue(all(n == 0 for n in observed[:3]))
        self.assertTrue(all(n >= 3 for n in observed[3:]))
        self.assertEqual(len(queried), len(set(queried)))


class CcassRangeApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        import db
        cls._db = db
        cls._orig = (db.DATA_DIR, db.META_DB_PATH, db.UPLOAD_DIR)
        db.DATA_DIR = cls.tmp.name
        db.META_DB_PATH = os.path.join(cls.tmp.name, '_meta.db')
        db.UPLOAD_DIR = os.path.join(cls.tmp.name, 'uploads')
        from fastapi.testclient import TestClient
        import app as app_module
        cls.app_module = app_module
        cls.client = TestClient(app_module.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        cls._db.DATA_DIR, cls._db.META_DB_PATH, cls._db.UPLOAD_DIR = cls._orig
        cls.tmp.cleanup()
        reset_ccass_backfill_state()

    def setUp(self):
        reset_ccass_backfill_state()
        self.app_module._fetch_jobs.clear()

    def _seed(self, code: str, sessions: int) -> None:
        from db import ensure_stock, get_stock_conn
        ensure_stock(code)
        dates = _weekdays_ending(sessions, datetime(2026, 10, 23))
        with get_stock_conn(code) as conn:
            for i, trade_date in enumerate(dates):
                conn.execute(
                    "INSERT INTO ccass_total (trade_date, total_shares, pct_of_issued) VALUES (?, ?, ?)",
                    (trade_date, 100000 + i, 20.5),
                )
                conn.execute(
                    """INSERT INTO ccass_participants
                       (trade_date, participant_id, participant_name, shares, pct_of_issued)
                       VALUES (?, ?, ?, ?, ?)""",
                    (trade_date, 'B00001', 'Example Broker', 1000 + i, 1.0),
                )
                conn.execute(
                    """INSERT INTO hk_connect (trade_date, shares, pct_of_issued, shares_change)
                       VALUES (?, ?, ?, ?)""",
                    (trade_date, 500 + i, 0.4, 10),
                )
                conn.execute(
                    """INSERT INTO ccass_daily_changes
                       (trade_date, participant_id, participant_name, shares, shares_change)
                       VALUES (?, ?, ?, ?, ?)""",
                    (trade_date, 'B00001', 'Example Broker', 1000 + i, 10),
                )

    def test_total_and_dates_follow_the_requested_window(self):
        code = '00993'
        self._seed(code, 80)
        default_rows = self.client.get(f'/api/stock/{code}/ccass/total')
        self.assertEqual(default_rows.status_code, 200)
        self.assertEqual(len(default_rows.json()), 60)
        self.assertEqual(len(self.client.get(f'/api/stock/{code}/ccass/total?days=30').json()), 30)
        self.assertEqual(len(self.client.get(f'/api/stock/{code}/ccass/total?days=365').json()), 80)
        self.assertEqual(self.client.get(f'/api/stock/{code}/ccass/total?days=366').status_code, 422)
        dates = self.client.get(f'/api/stock/{code}/ccass/dates?days=30')
        self.assertEqual(len(dates.json()['dates']), 30)
        hk = self.client.get(f'/api/stock/{code}/hk-connect')
        self.assertEqual(len(hk.json()), 60)

    def test_capital_flow_accepts_a_year_and_rejects_beyond_it(self):
        code = '00994'
        self._seed(code, 5)
        ok = self.client.get(f'/api/stock/{code}/capital-flow?days=180')
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(len(ok.json()['daily_flows']), 5)
        self.assertGreaterEqual(len(ok.json()['available_dates']), 5)
        self.assertEqual(self.client.get(f'/api/stock/{code}/capital-flow?days=400').status_code, 422)

    def test_ensure_starts_one_backfill_and_does_not_repeat_it(self):
        code = '00995'
        self._seed(code, 10)
        calls = []

        def fake_leader(code_arg, state, progress_callback=None, runner=None):
            calls.append((code_arg, state['target_days']))
            if progress_callback:
                progress_callback(1, 1, '2026-10-23')
            state['status'] = 'done'
            state['fetched'] = 0
            return 0

        with patch('services.ccass_range.run_ccass_backfill_leader', side_effect=fake_leader):
            first = self.client.post(f'/api/stock/{code}/ccass/ensure?days=180')
            self.assertEqual(first.status_code, 200)
            body = first.json()
            self.assertFalse(body['sufficient'])
            self.assertEqual(body['available_days'], 10)
            self.assertEqual(body['backfill'], 'running')
            self.assertTrue(body['job_id'])
            deadline = time.time() + 2
            status = None
            while time.time() < deadline:
                status = self.client.get(f"/api/jobs/{body['job_id']}").json()
                if status['status'] in ('done', 'error'):
                    break
                time.sleep(0.02)
            self.assertEqual(status['status'], 'done')
            self.assertEqual(calls, [(code, 180)])

            second = self.client.post(f'/api/stock/{code}/ccass/ensure?days=180')
            self.assertEqual(second.status_code, 200)
            self.assertEqual(second.json()['backfill'], 'done')
            self.assertEqual(calls, [(code, 180)])

    def test_frontend_selector_is_the_fixed_range(self):
        root = os.path.join(os.path.dirname(__file__), '..', '..')
        with open(os.path.join(root, 'frontend/src/components/CcassTab.tsx'), encoding='utf-8') as fh:
            ccass = fh.read()
        with open(os.path.join(root, 'frontend/src/components/CapitalFlowTab.tsx'), encoding='utf-8') as fh:
            flow = fh.read()
        self.assertIn('[30, 60, 90, 180, 365]', ccass)
        self.assertIn('useState(60)', ccass)
        self.assertNotIn('slice(-30)', ccass)
        self.assertIn('90, 180, 365', flow)
        self.assertIn('ccassBackfillShort', ccass)
        self.assertIn('ccassBackfillShort', flow)


if __name__ == '__main__':
    unittest.main()
