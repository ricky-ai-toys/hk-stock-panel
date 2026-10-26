"""
Cost Structure & Selling Pressure Analysis Engine.
Analyzes shareholder cost basis relative to current price to estimate selling pressure.
"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# English aliases for common CCASS participant IDs (HKEX traditional Chinese name -> English)
BROKER_EN_NAMES = {
    'C00010': 'Citibank',
    'C00019': 'HSBC Hong Kong',
    'C00039': 'Bank of China (HK)',
    'C00042': 'CMB Wing Lung Bank',
    'C00088': 'China Merchants Bank',
    'C00093': 'BNP Paribas',
    'C00111': 'Societe Generale',
    'C00113': 'ABN AMRO Clearing Bank',
    'C00155': 'Hang Seng Bank',
    'B01130': 'BOC International',
    'B01224': 'MLFE (Merrill Lynch)',
    'B01228': 'CITIC Securities Brokerage (HK)',
    'B01274': 'Morgan Stanley HK Securities',
    'B01487': 'China Renaissance Securities (HK)',
    'B01590': 'Interactive Brokers HK',
    'B01610': 'KGI Asia',
    'B01654': 'CICC HK Securities',
    'B01829': 'Huatai Financial Holdings (HK)',
    'B01893': 'China Merchants Securities (HK)',
    'B01904': 'Valuable Capital',
    'B01955': 'Futu Securities International (HK)',
    'B01963': 'TF International Securities & Futures',
    'B02009': 'Jin Yu Fu Securities',
    'B02142': 'Tiger Brokers (HK) Global',
    'A00003': 'CSDC (Mainland Connect SH)',
    'A00004': 'CSDC (Mainland Connect SZ)',
    'A00005': 'CSDC (Hong Kong Connect)',
}


def _get_current_price(conn) -> float:
    """Get latest closing price from daily_trading."""
    row = conn.execute("SELECT close FROM daily_trading ORDER BY trade_date DESC LIMIT 1").fetchone()
    return row['close'] if row and row['close'] else 0.0


def _classify_pressure(profit_pct) -> str:
    """Classify selling pressure level based on profit percentage."""
    if profit_pct is None:
        return 'unknown'
    if profit_pct > 50:
        return 'heavy'
    if profit_pct >= 20:
        return 'moderate'
    if profit_pct >= 0:
        return 'low'
    return 'underwater'


def _get_cost_bucket(profit_pct) -> str:
    """Assign shares to cost bucket based on profit percentage."""
    if profit_pct is None:
        return 'unknown'
    if profit_pct < -30:
        return 'deep_underwater'
    if profit_pct < -5:
        return 'underwater'
    if profit_pct < 5:
        return 'at_cost'
    if profit_pct < 30:
        return 'moderate_profit'
    if profit_pct < 80:
        return 'good_profit'
    return 'heavy_profit'


def _bucket_order() -> list:
    return [
        ('deep_underwater', 'deep_underwater'),
        ('underwater', 'underwater'),
        ('at_cost', 'at_cost'),
        ('moderate_profit', 'moderate_profit'),
        ('good_profit', 'good_profit'),
        ('heavy_profit', 'heavy_profit'),
    ]


def analyze_cost_structure(stock_code: str) -> dict:
    """
    Analyze shareholder cost structure and selling pressure.
    Returns dict with shareholders, cost_buckets, investor_type_breakdown,
    broker_concentration, pressure_score, current_price.
    """
    from db import get_stock_conn, init_stock_db
    code = stock_code.zfill(5)

    # Initialize tables BEFORE opening the main connection to avoid nested lock
    init_stock_db(code)

    with get_stock_conn(code) as conn:
        current_price = _get_current_price(conn)
        if current_price <= 0:
            return {
                'current_price': 0,
                'shareholders': [],
                'cost_buckets': [],
                'investor_type_breakdown': [],
                'broker_concentration': [],
                'pressure_score': 0,
                'total_analyzed_shares': 0,
            }

        # Get latest CCASS date
        latest_date_row = conn.execute("SELECT MAX(trade_date) as d FROM ccass_participants").fetchone()
        latest_date = latest_date_row['d'] if latest_date_row else None
        if not latest_date:
            return {
                'current_price': current_price,
                'shareholders': [],
                'cost_buckets': [],
                'investor_type_breakdown': [],
                'broker_concentration': [],
                'pressure_score': 0,
                'total_analyzed_shares': 0,
            }

        # Get shareholder attributions joined with current CCASS holdings
        attributions = conn.execute("""
            SELECT sa.*, cp.shares as shares_current, cp.participant_name as cp_name
            FROM shareholder_attribution sa
            LEFT JOIN ccass_participants cp ON sa.participant_id = cp.participant_id AND cp.trade_date = ?
        """, (latest_date,)).fetchall()

        shareholders = []
        for att in attributions:
            cost_hkd = att['cost_hkd']
            shares_current = att['shares_current'] or 0
            shares_baseline = att['shares_baseline'] or 0

            if cost_hkd and cost_hkd > 0:
                profit_pct = (current_price - cost_hkd) / cost_hkd * 100
                floating_profit = shares_current * (current_price - cost_hkd)
            else:
                profit_pct = None
                floating_profit = None

            pressure_level = _classify_pressure(profit_pct)

            shareholders.append({
                'name': att['shareholder_name'],
                'shares': shares_baseline,
                'shares_current': shares_current,
                'cost_hkd': cost_hkd,
                'investor_type': att['investor_type'] or 'Unknown',
                'unlock_date': att['unlock_date'],
                'participant_id': att['participant_id'],
                'participant_name': att['cp_name'] or att['participant_name'],
                'profit_pct': round(profit_pct, 2) if profit_pct is not None else None,
                'floating_profit': round(floating_profit, 0) if floating_profit is not None else None,
                'pressure_level': pressure_level,
                'confidence': att['confidence'],
            })

        total_analyzed_shares = sum(s['shares_current'] for s in shareholders)

        # === Cost Buckets ===
        bucket_shares: dict[str, float] = {b[0]: 0 for b in _bucket_order()}
        bucket_shareholders: dict[str, list] = {b[0]: [] for b in _bucket_order()}

        for s in shareholders:
            if s['shares_current'] <= 0:
                continue
            bucket = _get_cost_bucket(s['profit_pct'])
            if bucket in bucket_shares:
                bucket_shares[bucket] += s['shares_current']
                bucket_shareholders[bucket].append({
                    'name': s['name'],
                    'shares': s['shares_current'],
                })

        cost_buckets = []
        for bucket_key, _ in _bucket_order():
            shares_val = bucket_shares[bucket_key]
            pct = (shares_val / total_analyzed_shares * 100) if total_analyzed_shares > 0 else 0
            # Sort shareholders in this bucket by shares desc, take top 3
            top_sh = sorted(bucket_shareholders[bucket_key], key=lambda x: x['shares'], reverse=True)[:3]
            cost_buckets.append({
                'bucket': bucket_key,
                'shares': int(shares_val),
                'pct_of_total': round(pct, 2),
                'main_shareholders': [sh['name'] for sh in top_sh],
            })

        # === Investor Type Breakdown ===
        type_data: dict[str, dict] = {}
        for s in shareholders:
            itype = s['investor_type'] or 'Unknown'
            if itype not in type_data:
                type_data[itype] = {'shares': 0, 'total_cost_weighted': 0.0, 'count': 0}
            type_data[itype]['shares'] += s['shares_current']
            if s['cost_hkd'] and s['shares_current'] > 0:
                type_data[itype]['total_cost_weighted'] += s['cost_hkd'] * s['shares_current']
            type_data[itype]['count'] += 1

        investor_type_breakdown = []
        for itype, data in type_data.items():
            avg_cost = (data['total_cost_weighted'] / data['shares']) if data['shares'] > 0 and data['total_cost_weighted'] > 0 else None
            pct = (data['shares'] / total_analyzed_shares * 100) if total_analyzed_shares > 0 else 0
            investor_type_breakdown.append({
                'investor_type': itype,
                'shares': data['shares'],
                'pct': round(pct, 2),
                'avg_cost': round(avg_cost, 4) if avg_cost else None,
                'count': data['count'],
            })
        investor_type_breakdown.sort(key=lambda x: x['shares'], reverse=True)

        # === Broker Concentration ===
        broker_data: dict[str, dict] = {}
        for s in shareholders:
            pid = s['participant_id']
            if not pid:
                continue
            if pid not in broker_data:
                broker_data[pid] = {
                    'participant_id': pid,
                    'participant_name': s['participant_name'] or pid,
                    'shareholder_count': 0,
                    'total_shares': 0,
                }
            broker_data[pid]['shareholder_count'] += 1
            broker_data[pid]['total_shares'] += s['shares_current']

        broker_concentration = sorted(broker_data.values(), key=lambda x: x['shareholder_count'], reverse=True)

        # === Pressure Score ===
        score = _compute_pressure_score(conn, shareholders, current_price, latest_date, total_analyzed_shares, bucket_shares)

        return {
            'current_price': round(current_price, 4),
            'shareholders': sorted(shareholders, key=lambda x: x['shares_current'], reverse=True),
            'cost_buckets': cost_buckets,
            'investor_type_breakdown': investor_type_breakdown,
            'broker_concentration': broker_concentration,
            'pressure_score': score,
            'total_analyzed_shares': total_analyzed_shares,
            'latest_date': latest_date,
        }


def _compute_pressure_score(conn, shareholders, current_price, latest_date, total_analyzed_shares, bucket_shares) -> int:
    """Compute a 0-100 selling pressure score."""
    score = 0

    # 1. Profit bucket pressure (max 40 points)
    # heavy_profit = most pressure, good_profit = moderate
    if total_analyzed_shares > 0:
        heavy_profit_pct = bucket_shares.get('heavy_profit', 0) / total_analyzed_shares * 100
        good_profit_pct = bucket_shares.get('good_profit', 0) / total_analyzed_shares * 100
        moderate_profit_pct = bucket_shares.get('moderate_profit', 0) / total_analyzed_shares * 100

        profit_score = min(40, heavy_profit_pct * 0.6 + good_profit_pct * 0.35 + moderate_profit_pct * 0.15)
        score += profit_score

    # 2. Upcoming unlocks within 30 days (max 25 points)
    today = datetime.now().date()
    unlock_30d_end = today + timedelta(days=30)
    upcoming_unlock_shares = 0
    for s in shareholders:
        if s['unlock_date']:
            try:
                ud = datetime.strptime(s['unlock_date'], '%Y-%m-%d').date()
                if today <= ud <= unlock_30d_end:
                    upcoming_unlock_shares += s['shares'] or 0
            except (ValueError, TypeError):
                pass

    if total_analyzed_shares > 0:
        unlock_pct = upcoming_unlock_shares / total_analyzed_shares * 100
        unlock_score = min(25, unlock_pct * 2.5)
        score += unlock_score

    # 3. Recent selloff velocity (max 20 points)
    # Check shareholder_selloff for last 5 days of net selling
    selloff_start = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
    recent_selloffs = conn.execute("""
        SELECT shareholder_name, SUM(shares_change) as total_change
        FROM shareholder_selloff
        WHERE trade_date >= ? AND shares_change < 0
        GROUP BY shareholder_name
    """, (selloff_start,)).fetchall()

    total_recent_sold = 0
    for r in recent_selloffs:
        total_recent_sold += abs(r['total_change'] or 0)

    if total_analyzed_shares > 0:
        selloff_pct = total_recent_sold / total_analyzed_shares * 100
        selloff_score = min(20, selloff_pct * 2.0)
        score += selloff_score

    # 4. CCASS outflow (max 15 points) - total CCASS net change over last 5 days
    ccass_start_row = conn.execute(
        "SELECT trade_date FROM ccass_total WHERE trade_date <= ? ORDER BY trade_date DESC LIMIT 1 OFFSET 5",
        (latest_date,)
    ).fetchone()
    if ccass_start_row:
        start_total = conn.execute(
            "SELECT total_shares FROM ccass_total WHERE trade_date = ?",
            (ccass_start_row['trade_date'],)
        ).fetchone()
        end_total = conn.execute(
            "SELECT total_shares FROM ccass_total WHERE trade_date = ?",
            (latest_date,)
        ).fetchone()
        if start_total and end_total and total_analyzed_shares > 0:
            net_ccass_change = end_total['total_shares'] - start_total['total_shares']
            # Outflow increases pressure
            if net_ccass_change < 0:
                outflow_pct = abs(net_ccass_change) / total_analyzed_shares * 100
                outflow_score = min(15, outflow_pct * 3.0)
                score += outflow_score

    return int(min(100, round(score)))


def get_capital_flow(stock_code: str, days: int = 5, end_date: str | None = None) -> dict:
    """
    Generate capital flow / Sankey data showing shareholder → broker → buy/sell flows.
    end_date lets users inspect historical rolling windows, not only the latest window.
    """
    from db import get_stock_conn, init_stock_db
    code = stock_code.zfill(5)

    # Initialize tables BEFORE opening the main connection to avoid nested lock
    init_stock_db(code)

    with get_stock_conn(code) as conn:
        # Get latest date
        latest_row = conn.execute("SELECT MAX(trade_date) as d FROM ccass_daily_changes").fetchone()
        if not latest_row or not latest_row['d']:
            return {'nodes': [], 'links': [], 'top_inflows': [], 'top_outflows': [], 'daily_flows': [], 'shareholder_flows': []}

        latest_date = latest_row['d']

        # Get date range for daily data. If end_date is provided, take the rolling window ending on/before it.
        if end_date:
            date_rows = conn.execute(
                """
                SELECT DISTINCT trade_date FROM ccass_daily_changes
                WHERE trade_date <= ?
                ORDER BY trade_date DESC LIMIT ?
                """,
                (end_date, days)
            ).fetchall()
        else:
            date_rows = conn.execute(
                "SELECT DISTINCT trade_date FROM ccass_daily_changes ORDER BY trade_date DESC LIMIT ?",
                (days,)
            ).fetchall()
        target_dates = [r['trade_date'] for r in reversed(date_rows)]
        if not target_dates:
            return {'nodes': [], 'links': [], 'top_inflows': [], 'top_outflows': [], 'daily_flows': [], 'shareholder_flows': [], 'available_dates': []}

        available_date_rows = conn.execute(
            "SELECT DISTINCT trade_date FROM ccass_daily_changes ORDER BY trade_date DESC LIMIT 365"
        ).fetchall()
        available_dates = [r['trade_date'] for r in available_date_rows]

        # Get shareholder attributions
        attributions = conn.execute("SELECT * FROM shareholder_attribution").fetchall()
        pid_to_sh: dict[str, dict] = {}
        for att in attributions:
            pid = att['participant_id']
            pid_to_sh[pid] = {
                'name': att['shareholder_name'],
                'investor_type': att['investor_type'],
                'shares_baseline': att['shares_baseline'] or 0,
            }

        # Get changes over the period for top participants
        earliest_date = target_dates[0]
        latest_d = target_dates[-1]

        # Aggregate net change per participant over the period
        period_changes = conn.execute("""
            SELECT participant_id, participant_name,
                   SUM(shares_change) as net_change
            FROM ccass_daily_changes
            WHERE trade_date >= ? AND trade_date <= ?
            GROUP BY participant_id
            ORDER BY ABS(SUM(shares_change)) DESC
        """, (earliest_date, latest_d)).fetchall()

        # Get latest holdings per participant for context
        latest_p = conn.execute(
            "SELECT participant_id, shares FROM ccass_participants WHERE trade_date = ?",
            (latest_d,)
        ).fetchall()
        pid_shares = {r['participant_id']: r['shares'] for r in latest_p}

        # Build top inflows / outflows lists
        inflows = []
        outflows = []
        for ch in period_changes:
            nc = ch['net_change'] or 0
            if nc == 0:
                continue
            sh_info = pid_to_sh.get(ch['participant_id'])
            entry = {
                'participant_id': ch['participant_id'],
                'participant_name': ch['participant_name'],
                'participant_name_en': BROKER_EN_NAMES.get(ch['participant_id']),
                'net_change': nc,
                'current_shares': pid_shares.get(ch['participant_id'], 0),
                'attributed_shareholder': sh_info['name'] if sh_info else None,
            }
            if nc > 0:
                inflows.append(entry)
            else:
                outflows.append(entry)

        top_inflows = sorted(inflows, key=lambda x: x['net_change'], reverse=True)[:10]
        top_outflows = sorted(outflows, key=lambda x: x['net_change'])[:10]

        # === Daily flows for stacked bar chart (top 10 brokers by absolute change) ===
        top_pids = set()
        # Build ordered list of top PIDs (by absolute period change) and a display-name map
        top_pid_list = []
        for ch in sorted(period_changes, key=lambda x: abs(x['net_change'] or 0), reverse=True)[:10]:
            if ch['participant_id'] not in top_pids:
                top_pids.add(ch['participant_id'])
                top_pid_list.append(ch['participant_id'])
        pid_label: dict[str, str] = {}
        for pid in top_pid_list:
            ch = next((c for c in period_changes if c['participant_id'] == pid), None)
            if ch:
                raw_name = ch['participant_name'] or pid
                # Truncate long CJK names to ~10 display chars for chart readability
                if len(raw_name) > 10:
                    raw_name = raw_name[:10] + '…'
                pid_label[pid] = raw_name
            else:
                pid_label[pid] = pid

        daily_flows = []
        for d in target_dates:
            day_changes = conn.execute("""
                SELECT participant_id, participant_name, shares_change
                FROM ccass_daily_changes WHERE trade_date = ?
            """, (d,)).fetchall()
            day_entry: dict = {'date': d, '_pid_map': pid_label}
            for dc in day_changes:
                if dc['participant_id'] in top_pids:
                    value = dc['shares_change'] or 0
                    # Use PID as stable key for the new frontend.
                    day_entry[dc['participant_id']] = value
                    # Also expose display-label key so cached/old frontend bundles still render.
                    day_entry[pid_label.get(dc['participant_id'], dc['participant_id'])] = value
            daily_flows.append(day_entry)

        # Top broker display names (in same order as top_pid_list for consistent coloring).
        # Keep top_brokers as a string list for backward compatibility with cached frontend bundles.
        # Stable PID metadata is exposed separately for the new frontend.
        top_brokers = [pid_label[pid] for pid in top_pid_list]
        top_broker_meta = [{'pid': pid, 'label': pid_label[pid], 'name_en': BROKER_EN_NAMES.get(pid)} for pid in top_pid_list]

        # === Shareholder flow visualization data ===
        # For known shareholders, show their attributed broker and net direction
        shareholder_flows = []
        for att in attributions:
            pid = att['participant_id']
            # Get net change for this participant over period
            pc = next((c for c in period_changes if c['participant_id'] == pid), None)
            net = pc['net_change'] if pc else 0
            current_shares = pid_shares.get(pid, 0)
            shareholder_flows.append({
                'shareholder_name': att['shareholder_name'],
                'participant_id': pid,
                'participant_name': att['participant_name'] or (pc['participant_name'] if pc else pid),
                'shares_baseline': att['shares_baseline'] or 0,
                'shares_current': current_shares,
                'net_change': net,
                'investor_type': att['investor_type'] or 'Unknown',
            })

        # Sort by absolute net change
        shareholder_flows.sort(key=lambda x: abs(x['net_change']), reverse=True)

        # === Sankey nodes/links (simplified) ===
        nodes = []
        links = []
        node_idx: dict[str, int] = {}

        def add_node(name, level, category):
            key = f"{level}:{name}"
            if key not in node_idx:
                node_idx[key] = len(nodes)
                nodes.append({'name': name, 'level': level, 'category': category})
            return node_idx[key]

        # Level 2 destinations
        holding_id = add_node('持有/增持', 2, 'destination')
        selling_id = add_node('减持/卖出', 2, 'destination')

        # Process known shareholders
        for sf in shareholder_flows:
            if sf['shares_current'] <= 0 and sf['net_change'] >= 0:
                continue
            sh_id = add_node(sf['shareholder_name'], 0, 'shareholder')
            br_name = sf['participant_name'] or sf['participant_id']
            br_id = add_node(br_name, 1, 'broker')
            # shareholder -> broker
            flow_val = max(sf['shares_current'], abs(sf['net_change']), 1)
            links.append({'source': sh_id, 'target': br_id, 'value': flow_val})
            # broker -> destination
            if sf['net_change'] < 0:
                links.append({'source': br_id, 'target': selling_id, 'value': abs(sf['net_change'])})
            elif sf['net_change'] > 0:
                links.append({'source': br_id, 'target': holding_id, 'value': sf['net_change']})

        # Unknown/Retail for top inflows not attributed
        unknown_id = add_node('散户/未知', 0, 'retail')
        for inf in top_inflows[:5]:
            if inf['participant_id'] not in pid_to_sh:
                br_name = inf['participant_name'] or inf['participant_id']
                br_id = add_node(br_name, 1, 'broker')
                links.append({'source': unknown_id, 'target': br_id, 'value': inf['net_change']})
                links.append({'source': br_id, 'target': holding_id, 'value': inf['net_change']})

        return {
            'nodes': nodes,
            'links': links,
            'top_inflows': top_inflows,
            'top_outflows': top_outflows,
            'daily_flows': daily_flows,
            'top_brokers': top_brokers,
            'top_broker_meta': top_broker_meta,
            'shareholder_flows': shareholder_flows,
            'period_start': earliest_date,
            'period_end': latest_d,
            'available_dates': available_dates,
        }


def scenario_analysis(stock_code: str) -> dict:
    """
    Sell pressure scenario analysis — optimistic/base/pessimistic.
    Estimates potential selling volume and price impact under different scenarios.
    """
    from db import get_stock_conn
    code = stock_code.zfill(5)

    cost = analyze_cost_structure(code)
    current_price = cost['current_price']
    shareholders = cost['shareholders']
    pressure_score = cost['pressure_score']

    # Get average daily volume for impact estimation
    avg_vol = 0
    unlocks_30d = []
    unlocks_90d = []
    with get_stock_conn(code) as conn:
        avg_vol_row = conn.execute("""
            SELECT AVG(volume) as v FROM daily_trading ORDER BY trade_date DESC LIMIT 30
        """).fetchone()
        if avg_vol_row and avg_vol_row['v']:
            avg_vol = avg_vol_row['v']

        today = datetime.now().strftime('%Y-%m-%d')
        d30 = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
        d90 = (datetime.now() + timedelta(days=90)).strftime('%Y-%m-%d')

        unlocks_30d = conn.execute("""
            SELECT * FROM unlock_calendar WHERE unlock_date >= ? AND unlock_date <= ? ORDER BY unlock_date
        """, (today, d30)).fetchall()
        unlocks_90d = conn.execute("""
            SELECT * FROM unlock_calendar WHERE unlock_date > ? AND unlock_date <= ? ORDER BY unlock_date
        """, (d30, d90)).fetchall()

    unlock_30d_shares = sum((u['shares'] or 0) for u in unlocks_30d)
    unlock_90d_shares = sum((u['shares'] or 0) for u in unlocks_90d)

    # Calculate heavy profit shares (most likely to sell)
    heavy_profit_shares = sum(
        s['shares_current'] or 0
        for s in shareholders
        if s.get('pressure_level') == 'heavy' and (s.get('profit_pct') or 0) > 50
    )
    moderate_profit_shares = sum(
        s['shares_current'] or 0
        for s in shareholders
        if s.get('pressure_level') in ('heavy', 'moderate')
    )
    total_analyzed = sum((s['shares_current'] or 0) for s in shareholders) or 1

    scenarios = {}

    # Optimistic: only forced sellers, 20% of heavy profit holders sell
    opt_sell = int(heavy_profit_shares * 0.2 + unlock_30d_shares * 0.3)
    scenarios['optimistic'] = {
        'name_zh': '🟢 乐观情景',
        'name_en': '🟢 Optimistic',
        'description_zh': '仅解禁股东小幅减持，获利盘卖出意愿低，市场承接力强',
        'description_en': 'Only forced selling from unlocks, low profit-taking motivation, strong market absorption',
        'estimated_sell_shares': opt_sell,
        'pct_of_freefloat': round(opt_sell / total_analyzed * 100, 1) if total_analyzed else 0,
        'days_to_absorb': round(opt_sell / avg_vol, 1) if avg_vol > 0 else 0,
        'price_impact_pct': round(-opt_sell / (avg_vol * 20) * 2, 1) if avg_vol > 0 else 0,
        'assumptions_zh': [
            f'解禁后30天内股东仅减持{int(unlock_30d_shares*0.3/10000)}万股（约30%解禁量）',
            f'浮盈>80%的股东仅卖出20%仓位（约{int(heavy_profit_shares*0.2/10000)}万股）',
            '市场日均成交量可承接，冲击有限',
        ],
        'assumptions_en': [
            f'Unlocked shareholders sell only 30% within 30 days (~{int(unlock_30d_shares*0.3/10000)}x10K shares)',
            f'Heavy profit holders (>80%) sell only 20% of positions (~{int(heavy_profit_shares*0.2/10000)}x10K shares)',
            'Daily volume can absorb selling without major impact',
        ],
    }

    # Base case: moderate selling
    base_sell = int(moderate_profit_shares * 0.3 + unlock_30d_shares * 0.6 + unlock_90d_shares * 0.2)
    scenarios['base'] = {
        'name_zh': '🟡 基准情景',
        'name_en': '🟡 Base Case',
        'description_zh': '解禁股东逐步减持，部分获利盘兑现，抛压适中',
        'description_en': 'Phased selling from unlocked shareholders, partial profit-taking, moderate pressure',
        'estimated_sell_shares': base_sell,
        'pct_of_freefloat': round(base_sell / total_analyzed * 100, 1) if total_analyzed else 0,
        'days_to_absorb': round(base_sell / avg_vol, 1) if avg_vol > 0 else 0,
        'price_impact_pct': round(-base_sell / (avg_vol * 15) * 3, 1) if avg_vol > 0 else 0,
        'assumptions_zh': [
            f'解禁股东减持60%（30天内）+ 90天内解禁减持20%',
            f'浮盈>20%的股东卖出30%仓位（约{int(moderate_profit_shares*0.3/10000)}万股）',
            '南向资金和机构承接部分抛压',
        ],
        'assumptions_en': [
            f'60% of 30d unlocks sold + 20% of 90d unlocks',
            f'Profit holders (>20%) sell 30% (~{int(moderate_profit_shares*0.3/10000)}x10K shares)',
            'Southbound and institutions absorb partial selling',
        ],
    }

    # Pessimistic: heavy selling
    pess_sell = int(moderate_profit_shares * 0.5 + unlock_30d_shares * 0.9 + unlock_90d_shares * 0.5)
    scenarios['pessimistic'] = {
        'name_zh': '🔴 悲观情景',
        'name_en': '🔴 Pessimistic',
        'description_zh': '老股东集中减持，获利盘大量涌出，可能触发连锁抛售',
        'description_en': 'Concentrated selling from early shareholders, heavy profit-taking, potential cascade',
        'estimated_sell_shares': pess_sell,
        'pct_of_freefloat': round(pess_sell / total_analyzed * 100, 1) if total_analyzed else 0,
        'days_to_absorb': round(pess_sell / avg_vol, 1) if avg_vol > 0 else 0,
        'price_impact_pct': round(-pess_sell / (avg_vol * 10) * 5, 1) if avg_vol > 0 else 0,
        'assumptions_zh': [
            f'解禁股东减持90%（30天）+ 90天解禁减持50%',
            f'浮盈>20%的股东卖出50%仓位（约{int(moderate_profit_shares*0.5/10000)}万股）',
            '市场情绪恶化，卖盘难以承接，可能触发止损盘',
        ],
        'assumptions_en': [
            f'90% of 30d unlocks sold + 50% of 90d unlocks',
            f'Profit holders (>20%) sell 50% (~{int(moderate_profit_shares*0.5/10000)}x10K shares)',
            'Poor sentiment, overwhelmed buyers, potential stop-loss cascade',
        ],
    }

    return {
        'current_price': current_price,
        'avg_daily_volume': int(avg_vol),
        'pressure_score': pressure_score,
        'analyzed_shares': total_analyzed,
        'unlocks_30d': [dict(u) for u in unlocks_30d],
        'unlocks_30d_shares': unlock_30d_shares,
        'unlocks_90d_shares': unlock_90d_shares,
        'scenarios': scenarios,
    }


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO)
    code = sys.argv[1] if len(sys.argv) > 1 else '00000'
    result = analyze_cost_structure(code)
    print(f"Current price: {result['current_price']}")
    print(f"Pressure score: {result['pressure_score']}")
    print(f"Shareholders analyzed: {len(result['shareholders'])}")
