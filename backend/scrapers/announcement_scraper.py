"""
Announcement Scraper v2.1 — fetches company announcements from HKEX News (披露易).
Uses HKEX titleSearchServlet with stock list lookup from activestock JSON.

Anti-ban: uses anti_ban.AntiBanClient for rotating UA, rate limiting,
exponential backoff, and session rotation.
"""
import logging
import time
import json
import random
import os
from datetime import datetime, timedelta
from typing import Optional
from bs4 import BeautifulSoup

from .anti_ban import make_hkex_news_client

logger = logging.getLogger(__name__)

TITLE_SEARCH_URL = 'https://www1.hkexnews.hk/search/titleSearchServlet.do'
ACTIVE_STOCK_URL = 'https://www1.hkexnews.hk/ncms/script/eds/activestock_sehk_c.json'
BASE_PDF_URL = 'https://www1.hkexnews.hk'

# Category keyword mapping
CATEGORY_KEYWORDS = [
    ('业绩公告', ['业绩', '中期', '季度', '年报', '中报', '全年业绩', '中期业绩', '季度业绩']),
    ('回购', ['回购', '购回', '購回', 'repurchase', '股份回购', '股份購回', '购回股份']),
    ('增减持', ['增持', '减持', '权益变动', 'disclosure of interests', '股权变动']),
    ('配股/融资', ['配股', '配售', 'placing', '供股', '增发', '公开发售', '集资']),
    ('董事变动', ['董事', '委任', '辞任', 'director', '退任']),
    ('重大事项', ['重大交易', '收购', '出售', '须予披露', '非常重大', '关连交易', '内幕消息']),
    ('股息', ['股息', '分派', 'dividend', '派息', '派付']),
]

MATERIAL_CATEGORIES = {'配股/融资', '重大事项', '增减持'}

# Cache for stock list
_stock_list_cache = None
_stock_list_cache_time = None
STOCK_LIST_CACHE_TTL = 86400  # 24 hours

# Thread-local client
_tl = __import__('threading').local()


def _client():
    if not hasattr(_tl, 'client'):
        _tl.client = make_hkex_news_client()
    return _tl.client


def _get_stock_list() -> list[dict]:
    """Fetch and cache the active stock list from HKEX."""
    global _stock_list_cache, _stock_list_cache_time
    now = time.time()
    if _stock_list_cache and _stock_list_cache_time and (now - _stock_list_cache_time) < STOCK_LIST_CACHE_TTL:
        return _stock_list_cache

    for attempt in range(3):
        try:
            r = _client().get(
                ACTIVE_STOCK_URL,
                headers={"Accept": "application/json, */*; q=0.01"},
            )
            if r.status_code == 200:
                _stock_list_cache = r.json()
                _stock_list_cache_time = now
                return _stock_list_cache
        except Exception as e:
            logger.warning(f"Stock list fetch attempt {attempt+1} failed: {e}")
            time.sleep(1 + random.random())
    return _stock_list_cache or []


def _resolve_stock_id(stock_code: str) -> Optional[int]:
    """Map a 5-digit stock code to HKEX internal stock ID (i field)."""
    code = stock_code.zfill(5)
    stock_list = _get_stock_list()
    for item in stock_list:
        if item.get('c') == code:
            return item.get('i')
    return None


def _classify_title(title: str, long_text: str = '') -> tuple[str, bool]:
    """Classify announcement title into category. Returns (category, is_material)."""
    text = (title + ' ' + (long_text or '')).lower()
    for cat, keywords in CATEGORY_KEYWORDS:
        for kw in keywords:
            if kw.lower() in text:
                return cat, cat in MATERIAL_CATEGORIES
    return '其他', False


def _parse_date_time(dt_str: str) -> str:
    """Parse HKEX date format DD/MM/YYYY HH:MM to YYYY-MM-DD."""
    try:
        parts = dt_str.strip().split(' ')[0]
        d = datetime.strptime(parts, '%d/%m/%Y')
        return d.strftime('%Y-%m-%d')
    except Exception:
        return dt_str[:10]


def fetch_announcements(stock_code: str, start_date: str = None, end_date: str = None,
                        progress_callback=None) -> list[dict]:
    """Fetch announcements for a stock from HKEX."""
    code = stock_code.zfill(5)

    # Resolve stock ID
    stock_id = _resolve_stock_id(code)
    if not stock_id:
        logger.warning(f"Could not resolve stock ID for {code}")
        return []

    client = _client()

    # Date range
    if end_date is None:
        end_dt = datetime.now()
    else:
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    if start_date is None:
        start_dt = end_dt - timedelta(days=180)
    else:
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')

    all_results = []
    row_range = 100  # max per page
    loaded = 0

    if progress_callback:
        progress_callback(5, f'Fetching announcements for {code}')

    while True:
        params = {
            'sortDir': '0',
            'sortByOptions': 'DateTime',
            'category': '0',
            'market': 'SEHK',
            'stockId': str(stock_id),
            'documentType': '-1',
            'fromDate': start_dt.strftime('%Y%m%d'),
            'toDate': end_dt.strftime('%Y%m%d'),
            'title': '',
            'searchType': '1',
            't1code': '-2',
            't2Gcode': '-2',
            't2code': '-2',
            'rowRange': str(row_range),
            'lang': 'ZH',
        }

        try:
            r = client.get(
                TITLE_SEARCH_URL,
                params=params,
                headers={
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
        except Exception as e:
            logger.error(f"Failed to fetch announcements for {code}: {e}")
            return all_results

        try:
            data = r.json()
            result = json.loads(data.get('result', '[]'))
        except Exception as e:
            logger.error(f"Parse error for {code}: {e}")
            return all_results

        if not result:
            break

        for item in result:
            # Parse stock code (may contain multiple like "00700<br/>80700")
            raw_code = item.get('STOCK_CODE', '').replace('<br/>', '/').split('/')[0].strip()
            if raw_code != code:
                continue  # Skip if not our stock (can happen with warrants)

            title = item.get('TITLE', '').strip()
            long_text = BeautifulSoup(item.get('LONG_TEXT', ''), 'html.parser').get_text().strip()
            category, is_material = _classify_title(title, long_text)

            pdf_link = item.get('FILE_LINK', '')
            if pdf_link and not pdf_link.startswith('http'):
                pdf_link = BASE_PDF_URL + pdf_link

            all_results.append({
                'announce_date': _parse_date_time(item.get('DATE_TIME', '')),
                'title': title,
                'category': category,
                'pdf_url': pdf_link,
                'summary': long_text[:500] if long_text else '',
                'is_material': 1 if is_material else 0,
            })

        record_cnt = int(data.get('recordCnt', 0))
        loaded += len(result)
        if progress_callback:
            pct = min(80, int(loaded / max(record_cnt, 1) * 80) + 5)
            progress_callback(pct, f'Fetched {loaded} announcements')

        # Check if there are more pages
        has_next = data.get('hasNextRow', False)
        if not has_next or loaded >= record_cnt or len(result) < row_range:
            break

        # Page-to-page delay with jitter (anti-ban: avoid rapid pagination)
        time.sleep(1.0 + random.random() * 1.0)

    logger.info(f"Fetched {len(all_results)} announcements for {code}")
    return all_results


def save_announcements(stock_code: str, data: list[dict]) -> int:
    """Save announcements to DB, returning count of new entries."""
    from db import get_stock_conn
    code = stock_code.zfill(5)
    new_count = 0
    with get_stock_conn(code) as conn:
        for item in data:
            try:
                cursor = conn.execute("""
                    INSERT OR IGNORE INTO announcements (announce_date, title, category, pdf_url, summary, is_material)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    item['announce_date'], item['title'], item['category'],
                    item['pdf_url'], item['summary'], item.get('is_material', 0),
                ))
                if cursor.rowcount > 0:
                    new_count += 1
            except Exception as e:
                logger.error(f"Save announcement error: {e}")
    return new_count


def backfill_announcements(stock_code: str, days: int = 180, progress_callback=None) -> int:
    """Backfill announcements for a stock. Returns count of new records."""
    code = stock_code.zfill(5)
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=days)

    def _cb(pct, msg):
        if progress_callback:
            progress_callback(pct, msg)

    data = fetch_announcements(code, start_dt.strftime('%Y-%m-%d'), end_dt.strftime('%Y-%m-%d'), progress_callback=_cb)
    new_count = save_announcements(code, data)
    if progress_callback:
        progress_callback(100, f'Complete: {new_count} new announcements')
    logger.info(f"Announcements backfill complete for {code}: {new_count} new, {len(data)} total")
    return new_count


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    code = sys.argv[1] if len(sys.argv) > 1 else '00700'
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 90
    result = backfill_announcements(code, days=days, progress_callback=lambda p, m: print(f'{p}%: {m}'))
    print(f"Saved {result} new announcements for {code}")
