"""
Anomaly detection engine.
Identifies unusual CCASS movements that may signal selling, accumulation, or new positions.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Thresholds for anomaly detection
THRESHOLD_SINGLE_DAY_PCT = 0.3    # Single-day change > 0.3% of issued shares
THRESHOLD_3D_PCT = 0.5           # 3-day change > 0.5%
THRESHOLD_NEW_PARTICIPANT = 0.2  # New participant with > 0.2% of issued shares
THRESHOLD_VOLUME_MULTIPLE = 2.0  # Volume > 2x average


def detect_anomalies(stock_code: str, trade_date: str = None) -> list[dict]:
    """Detect anomalies for a given date."""
    from db import get_stock_conn
    code = stock_code.zfill(5)
    anomalies = []

    with get_stock_conn(code) as conn:
        if trade_date is None:
            latest = conn.execute("SELECT MAX(trade_date) as d FROM ccass_daily_changes").fetchone()
            if not latest or not latest['d']:
                return []
            trade_date = latest['d']

        # Get CCASS total for percentage calculation
        total_row = conn.execute("SELECT total_shares, pct_of_issued FROM ccass_total WHERE trade_date = ?", (trade_date,)).fetchone()
        total_shares = total_row['total_shares'] if total_row else 0
        issued_shares = int(total_shares / (total_row['pct_of_issued'] / 100)) if total_row and total_row['pct_of_issued'] else 0

        if issued_shares == 0:
            # Try stock_info
            si = conn.execute("SELECT value FROM stock_info WHERE key = 'issued_shares'").fetchone()
            if si:
                import json
                issued_shares = json.loads(si['value']) if si['value'] else 0

        # 1. Large single-day position changes
        changes = conn.execute("""
            SELECT cdc.*, sa.shareholder_name
            FROM ccass_daily_changes cdc
            LEFT JOIN shareholder_attribution sa ON cdc.participant_id = sa.participant_id
            WHERE cdc.trade_date = ?
            ORDER BY ABS(cdc.shares_change) DESC
        """, (trade_date,)).fetchall()

        for ch in changes:
            change = ch['shares_change'] or 0
            if issued_shares > 0:
                change_pct = abs(change) / issued_shares * 100
            else:
                change_pct = 0

            if change_pct >= THRESHOLD_SINGLE_DAY_PCT:
                direction = '净卖出' if change < 0 else '净买入'
                anomalies.append({
                    'type': 'large_change',
                    'severity': 'high' if change_pct >= 1.0 else 'medium',
                    'participant_id': ch['participant_id'],
                    'participant_name': ch['participant_name'],
                    'shareholder_name': ch['shareholder_name'],
                    'direction': direction,
                    'shares_change': change,
                    'change_pct_of_issued': round(change_pct, 3),
                    'message': f"{ch['participant_name']} {direction} {abs(change):,}股 ({change_pct:.2f}%总股本)"
                        + (f" [{ch['shareholder_name']}]" if ch['shareholder_name'] else ""),
                })

            # 3-day trend
            change_3d = ch['shares_change_3d'] or 0
            if issued_shares > 0:
                change_3d_pct = abs(change_3d) / issued_shares * 100
                if change_3d_pct >= THRESHOLD_3D_PCT and abs(change_3d) > abs(change):
                    direction = '持续减仓' if change_3d < 0 else '持续建仓'
                    anomalies.append({
                        'type': 'trend_3d',
                        'severity': 'high' if change_3d_pct >= 1.0 else 'medium',
                        'participant_id': ch['participant_id'],
                        'participant_name': ch['participant_name'],
                        'shareholder_name': ch['shareholder_name'],
                        'direction': direction,
                        'shares_change_3d': change_3d,
                        'change_pct_of_issued': round(change_3d_pct, 3),
                        'message': f"{ch['participant_name']} 3日{direction} {abs(change_3d):,}股 ({change_3d_pct:.2f}%)",
                    })

        # 2. New significant participants
        new_parts = conn.execute("""
            SELECT * FROM ccass_new_participants WHERE trade_date = ? AND is_new = 1
        """, (trade_date,)).fetchall()

        for np_ in new_parts:
            if issued_shares > 0 and np_['shares']:
                pct = np_['shares'] / issued_shares * 100
                if pct >= THRESHOLD_NEW_PARTICIPANT:
                    anomalies.append({
                        'type': 'new_participant',
                        'severity': 'high' if pct >= 1.0 else 'medium',
                        'participant_id': np_['participant_id'],
                        'participant_name': np_['participant_name'],
                        'shares': np_['shares'],
                        'pct_of_issued': round(pct, 3),
                        'message': f"新入席位: {np_['participant_name']} 持仓 {np_['shares']:,}股 ({pct:.2f}%)",
                    })

        # 3. Exited participants (was holding >0.3% now gone)
        exited = conn.execute("""
            SELECT * FROM ccass_new_participants WHERE trade_date = ? AND is_new = 0
        """, (trade_date,)).fetchall()

        # Get previous day holdings for exited
        prev_date_row = conn.execute("SELECT MAX(trade_date) FROM ccass_participants WHERE trade_date < ?", (trade_date,)).fetchone()
        if prev_date_row and prev_date_row[0]:
            prev_date = prev_date_row[0]
            for ex in exited:
                prev = conn.execute("SELECT shares FROM ccass_participants WHERE trade_date = ? AND participant_id = ?",
                                    (prev_date, ex['participant_id'])).fetchone()
                if prev and prev['shares'] and issued_shares > 0:
                    pct = prev['shares'] / issued_shares * 100
                    if pct >= THRESHOLD_SINGLE_DAY_PCT:
                        anomalies.append({
                            'type': 'exited_participant',
                            'severity': 'high' if pct >= 1.0 else 'medium',
                            'participant_id': ex['participant_id'],
                            'participant_name': ex['participant_name'],
                            'prev_shares': prev['shares'],
                            'pct_of_issued': round(pct, 3),
                            'message': f"席位清仓: {ex['participant_name']} 清空 {prev['shares']:,}股 ({pct:.2f}%)",
                        })

        # 4. HK Connect anomaly
        hk = conn.execute("SELECT * FROM hk_connect WHERE trade_date = ?", (trade_date,)).fetchone()
        if hk and hk['shares_change'] and issued_shares > 0:
            hk_pct = abs(hk['shares_change']) / issued_shares * 100
            if hk_pct >= THRESHOLD_SINGLE_DAY_PCT:
                direction = '南向净买入' if hk['shares_change'] > 0 else '南向净卖出'
                anomalies.append({
                    'type': 'hk_connect',
                    'severity': 'high' if hk_pct >= 1.0 else 'medium',
                    'direction': direction,
                    'shares_change': hk['shares_change'],
                    'change_pct_of_issued': round(hk_pct, 3),
                    'message': f"{direction} {abs(hk['shares_change']):,}股 ({hk_pct:.2f}%)",
                })

        # 5. Volume anomaly
        trade_row = conn.execute("SELECT * FROM daily_trading WHERE trade_date = ?", (trade_date,)).fetchone()
        if trade_row and trade_row['volume']:
            avg_row = conn.execute("""
                SELECT AVG(volume) as avg_vol FROM daily_trading
                WHERE trade_date < ? AND trade_date >= date(?, '-30 days')
            """, (trade_date, trade_date)).fetchone()
            if avg_row and avg_row['avg_vol'] and avg_row['avg_vol'] > 0:
                vol_ratio = trade_row['volume'] / avg_row['avg_vol']
                if vol_ratio >= THRESHOLD_VOLUME_MULTIPLE:
                    anomalies.append({
                        'type': 'volume_spike',
                        'severity': 'medium',
                        'volume': trade_row['volume'],
                        'avg_volume': int(avg_row['avg_vol']),
                        'ratio': round(vol_ratio, 1),
                        'price_change_pct': trade_row['change_pct'],
                        'message': f"放量: 成交量为30日均量的{vol_ratio:.1f}倍，股价{'涨' if (trade_row['change_pct'] or 0) > 0 else '跌'}{abs(trade_row['change_pct'] or 0):.2f}%",
                    })

    # Sort by severity
    severity_order = {'high': 0, 'medium': 1, 'low': 2}
    anomalies.sort(key=lambda x: severity_order.get(x.get('severity', 'low'), 3))

    return anomalies


def get_signal_score(stock_code: str, trade_date: str = None) -> dict:
    """
    Compute a composite signal score (0-100).
    Higher score = stronger selling/distribution signal.
    Lower score = accumulation signal.
    """
    anomalies = detect_anomalies(stock_code, trade_date)
    if not anomalies:
        return {'score': 50, 'signals': [], 'verdict': '无明显信号'}

    score = 50  # neutral
    sell_signals = 0
    buy_signals = 0

    for a in anomalies:
        weight = 3 if a['severity'] == 'high' else 1
        if a.get('direction') in ('净卖出', '持续减仓') or a['type'] == 'exited_participant':
            score += weight * 5
            sell_signals += 1
        elif a.get('direction') in ('净买入', '持续建仓') or a['type'] == 'new_participant':
            score -= weight * 5
            buy_signals += 1
        elif a.get('direction') == '南向净卖出':
            score += weight * 4
            sell_signals += 1
        elif a.get('direction') == '南向净买入':
            score -= weight * 4
            buy_signals += 1

    score = max(0, min(100, score))

    if score >= 75:
        verdict = '⚠️ 强烈减持信号'
    elif score >= 60:
        verdict = '📉 偏减持信号'
    elif score <= 25:
        verdict = '🟢 强烈吸筹信号'
    elif score <= 40:
        verdict = '📈 偏吸筹信号'
    else:
        verdict = '⚖️ 多空平衡'

    return {
        'score': score,
        'verdict': verdict,
        'sell_signals': sell_signals,
        'buy_signals': buy_signals,
        'anomalies': anomalies[:10],
    }


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO)
    code = sys.argv[1] if len(sys.argv) > 1 else '00700'
    signals = get_signal_score(code)
    print(f"Signal score: {signals['score']}/100 - {signals['verdict']}")
    for a in signals.get('anomalies', []):
        print(f"  [{a['severity']}] {a['message']}")
