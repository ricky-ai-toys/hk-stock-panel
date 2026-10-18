"""
Trading data scraper v2.1 — multi-source with fallback + anti-ban protection.
Primary: Tencent Finance (fast, Chinese HK stock data)
Fallback: Yahoo Finance → Sina Finance

Anti-ban measures (via anti_ban.AntiBanClient):
- Rotating User-Agent
- Rate limiting with jitter
- Exponential backoff on failure
- Session rotation after repeated failures
"""
import logging
import random
import json
from datetime import datetime, timedelta

from .anti_ban import make_tencent_client, make_yahoo_client, make_sina_client

logger = logging.getLogger(__name__)

# Thread-local clients
_tl = __import__('threading').local()


def _tencent():
    if not hasattr(_tl, 'tencent'):
        _tl.tencent = make_tencent_client()
    return _tl.tencent


def _yahoo():
    if not hasattr(_tl, 'yahoo'):
        _tl.yahoo = make_yahoo_client()
    return _tl.yahoo


def _sina():
    if not hasattr(_tl, 'sina'):
        _tl.sina = make_sina_client()
    return _tl.sina


def parse_number(text):
    if not text:
        return None
    text = str(text).strip().replace(',', '').replace(' ', '')
    try:
        return int(text) if '.' not in text else float(text)
    except (ValueError, TypeError):
        return None


# ============ Source 1: Tencent Finance ============

def fetch_stock_info_tencent(stock_code: str) -> dict:
    """Fetch basic stock info from Tencent."""
    code = stock_code.zfill(5)
    url = f'https://qt.gtimg.cn/q=hk{code}'

    try:
        r = _tencent().get(url)
        r.encoding = 'gbk'
        text = r.text

        parts = text.split('"')
        if len(parts) < 2:
            return {}
        fields = parts[1].split('~')
        if len(fields) < 50:
            return {}

        info = {
            'stock_code': code,
            'stock_name': fields[1] if len(fields) > 1 else '',
            'last_price': parse_number(fields[3]) if len(fields) > 3 else None,
            'change_pct': parse_number(fields[32]) if len(fields) > 32 else None,
            'change_amt': parse_number(fields[31]) if len(fields) > 31 else None,
            'volume': parse_number(fields[36]) if len(fields) > 36 else None,
            'turnover': parse_number(fields[37]) if len(fields) > 37 else None,
            'high': parse_number(fields[33]) if len(fields) > 33 else None,
            'low': parse_number(fields[34]) if len(fields) > 34 else None,
            'open': parse_number(fields[5]) if len(fields) > 5 else None,
            'prev_close': parse_number(fields[4]) if len(fields) > 4 else None,
            'market_cap': parse_number(fields[45]) if len(fields) > 45 else None,
            'pe_ratio': parse_number(fields[39]) if len(fields) > 39 else None,
            'week_52_high': parse_number(fields[41]) if len(fields) > 41 else None,
            'week_52_low': parse_number(fields[42]) if len(fields) > 42 else None,
            'lot_size': parse_number(fields[29]) if len(fields) > 29 else None,
            'source': 'tencent',
        }

        if info.get('turnover'):
            info['turnover'] = info['turnover'] * 10000  # 万港元 → 港元

        return info
    except Exception as e:
        logger.warning(f"Tencent info fetch failed for {code}: {e}")
        return {}


def fetch_daily_trading_tencent(stock_code: str, start_date: str = None, end_date: str = None) -> list[dict]:
    """Fetch daily kline from Tencent."""
    code = stock_code.zfill(5)

    if end_date is None:
        hkt_now = datetime.utcnow() + timedelta(hours=8)
        end_date = hkt_now.strftime('%Y-%m-%d')
    if start_date is None:
        start_dt = datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=365)
        start_date = start_dt.strftime('%Y-%m-%d')

    url = f'https://proxy.finance.qq.com/ifzqgtimg/appstock/app/hkfqkline/get?_var=kline_dayqfq&param=hk{code},day,{start_date},{end_date},800,qfq'

    try:
        r = _tencent().get(url)
        json_str = r.text.split('=', 1)[1]
        obj = json.loads(json_str)

        klines = obj.get('data', {}).get(f'hk{code}', {}).get('qfqday', [])
        if not klines:
            klines = obj.get('data', {}).get(f'hk{code}', {}).get('day', [])

        results = []
        prev_close = None
        for k in klines:
            if len(k) < 6:
                continue
            date_str = k[0]
            open_p = float(k[1])
            close = float(k[2])
            high = float(k[3])
            low = float(k[4])
            volume = int(float(k[5]))
            turnover = float(k[8]) * 10000 if len(k) > 8 else None

            change_pct = None
            if prev_close and prev_close > 0:
                change_pct = round((close - prev_close) / prev_close * 100, 2)
            prev_close = close

            results.append({
                'trade_date': date_str,
                'open': open_p,
                'high': high,
                'low': low,
                'close': close,
                'volume': volume,
                'turnover': turnover,
                'change_pct': change_pct,
            })

        logger.info(f"Tencent: fetched {len(results)} trading days for {code}")
        return results
    except Exception as e:
        logger.warning(f"Tencent trading fetch failed for {code}: {e}")
        return []


# ============ Source 2: Yahoo Finance ============

def fetch_stock_info_yahoo(stock_code: str) -> dict:
    """Fetch stock info from Yahoo Finance API (fallback)."""
    code = stock_code.zfill(5)
    yahoo_code = f'{code}.HK'
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_code}?range=1d&interval=1d'

    try:
        r = _yahoo().get(url)
        data = r.json()
        meta = data.get('chart', {}).get('result', [{}])[0].get('meta', {})

        info = {
            'stock_code': code,
            'stock_name': meta.get('shortName', meta.get('longName', '')),
            'last_price': meta.get('regularMarketPrice'),
            'prev_close': meta.get('chartPreviousClose') or meta.get('previousClose'),
            'market_cap': meta.get('marketCap'),
            'source': 'yahoo',
        }
        if info.get('last_price') and info.get('prev_close'):
            info['change_pct'] = round((info['last_price'] - info['prev_close']) / info['prev_close'] * 100, 2)

        return {k: v for k, v in info.items() if v is not None}
    except Exception as e:
        logger.warning(f"Yahoo info fetch failed for {code}: {e}")
        return {}


def fetch_daily_trading_yahoo(stock_code: str, start_date: str = None, end_date: str = None) -> list[dict]:
    """Fetch daily kline from Yahoo Finance (fallback)."""
    code = stock_code.zfill(5)
    yahoo_code = f'{code}.HK'

    if end_date is None:
        end_dt = datetime.utcnow() + timedelta(hours=8)
    else:
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    if start_date is None:
        start_dt = end_dt - timedelta(days=365)
    else:
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')

    period1 = int(start_dt.timestamp())
    period2 = int((end_dt + timedelta(days=1)).timestamp())

    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_code}?period1={period1}&period2={period2}&interval=1d'

    try:
        r = _yahoo().get(url)
        data = r.json()
        result = data.get('chart', {}).get('result', [{}])[0]

        timestamps = result.get('timestamp', [])
        quote = result.get('indicators', {}).get('quote', [{}])[0]

        results = []
        prev_close = None
        for i, ts in enumerate(timestamps):
            dt = datetime.fromtimestamp(ts)
            date_str = dt.strftime('%Y-%m-%d')
            open_p = quote.get('open', [None])[i]
            close = quote.get('close', [None])[i]
            high = quote.get('high', [None])[i]
            low = quote.get('low', [None])[i]
            volume = quote.get('volume', [None])[i]

            if close is None:
                continue

            change_pct = None
            if prev_close and prev_close > 0:
                change_pct = round((close - prev_close) / prev_close * 100, 2)
            prev_close = close

            results.append({
                'trade_date': date_str,
                'open': round(open_p, 3) if open_p else None,
                'high': round(high, 3) if high else None,
                'low': round(low, 3) if low else None,
                'close': round(close, 3),
                'volume': int(volume) if volume else 0,
                'turnover': None,
                'change_pct': change_pct,
            })

        logger.info(f"Yahoo: fetched {len(results)} trading days for {code}")
        return results
    except Exception as e:
        logger.warning(f"Yahoo trading fetch failed for {code}: {e}")
        return []


# ============ Source 3: Sina Finance (extra fallback) ============

def fetch_stock_info_sina(stock_code: str) -> dict:
    """Fetch from Sina Finance as third option."""
    code = stock_code.zfill(5)
    url = f'https://hq.sinajs.cn/list=rt_hk{code}'

    try:
        r = _sina().get(url)
        r.encoding = 'gbk'
        text = r.text
        parts = text.split('"')
        if len(parts) < 2:
            return {}
        fields = parts[1].split(',')
        if len(fields) < 10:
            return {}

        return {
            'stock_code': code,
            'stock_name': fields[0],
            'last_price': parse_number(fields[6]),
            'open': parse_number(fields[2]),
            'high': parse_number(fields[4]),
            'low': parse_number(fields[5]),
            'prev_close': parse_number(fields[3]),
            'volume': parse_number(fields[12]),
            'turnover': parse_number(fields[11]),
            'source': 'sina',
        }
    except Exception as e:
        logger.debug(f"Sina fetch failed: {e}")
        return {}


# ============ Unified API with fallback ============

def fetch_stock_info(stock_code: str) -> dict:
    """Fetch stock info, trying sources in order until one works."""
    # Add small delay before switching sources to avoid hammering
    info = fetch_stock_info_tencent(stock_code)
    if info.get('stock_name') and info.get('last_price'):
        return info

    logger.info(f"Tencent failed for {stock_code}, trying Yahoo...")
    import time; time.sleep(0.5 + random.random())
    info = fetch_stock_info_yahoo(stock_code)
    if info.get('stock_name') and info.get('last_price'):
        return info

    logger.info(f"Yahoo failed for {stock_code}, trying Sina...")
    import time; time.sleep(0.5 + random.random())
    info = fetch_stock_info_sina(stock_code)
    if info.get('stock_name') and info.get('last_price'):
        return info

    logger.error(f"All sources failed for stock info: {stock_code}")
    return {}


def fetch_daily_trading(stock_code: str, start_date: str = None, end_date: str = None) -> list[dict]:
    """Fetch daily trading data with fallback."""
    data = fetch_daily_trading_tencent(stock_code, start_date, end_date)
    if data and len(data) > 5:
        return data

    logger.info(f"Tencent trading data insufficient for {stock_code}, trying Yahoo...")
    import time; time.sleep(1 + random.random())
    data = fetch_daily_trading_yahoo(stock_code, start_date, end_date)
    if data:
        return data

    logger.error(f"All trading data sources failed for {stock_code}")
    return []


def save_trading_data(stock_code: str, data: list[dict]):
    """Save trading data to per-stock DB."""
    from db import get_stock_conn
    code = stock_code.zfill(5)
    with get_stock_conn(code) as conn:
        for d in data:
            conn.execute("""
                INSERT OR REPLACE INTO daily_trading
                (trade_date, open, high, low, close, volume, turnover, change_pct)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (d['trade_date'], d['open'], d['high'], d['low'], d['close'],
                  d['volume'], d.get('turnover'), d.get('change_pct')))


def save_stock_info(stock_code: str, info: dict):
    """Save stock info to stock_info key-value table."""
    from db import get_stock_conn
    code = stock_code.zfill(5)
    with get_stock_conn(code) as conn:
        for key, value in info.items():
            conn.execute("""
                INSERT OR REPLACE INTO stock_info (key, value, updated_at)
                VALUES (?, ?, datetime('now'))
            """, (key, json.dumps(value) if value is not None else None))


def backfill_trading(stock_code: str, start_date: str = None, end_date: str = None):
    """Backfill trading data + stock info."""
    from db import ensure_stock
    code = ensure_stock(stock_code)

    logger.info(f"Fetching trading data for {code}")
    data = fetch_daily_trading(code, start_date, end_date)
    if data:
        save_trading_data(code, data)
        logger.info(f"Saved {len(data)} trading days")

    logger.info(f"Fetching stock info for {code}")
    info = fetch_stock_info(code)
    if info:
        save_stock_info(code, info)
        logger.info(f"Stock info: {info.get('stock_name', '')} @ {info.get('last_price', '')}")

    return len(data)


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    if len(sys.argv) < 2:
        print("Usage: python trading_scraper.py <stock_code> [start_date] [end_date]")
        sys.exit(1)
    backfill_trading(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None, sys.argv[3] if len(sys.argv) > 3 else None)
