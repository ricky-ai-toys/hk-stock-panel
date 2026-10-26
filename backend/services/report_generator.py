"""
Report Generator — generates daily/weekly/monthly reports in Markdown format.
Two modes:
  - trader: public data only (price, CCASS, southbound, signals, announcements)
  - ir: includes shareholder attribution, selloff tracking, unlock calendar
"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _fmt_issued_pct(value) -> str:
    """HKEX leaves % of issued units blank for some ETFs. Don't crash the report."""
    if value is None:
        return '未披露'
    return f'{value:.2f}%'


def generate_report(stock_code: str, report_type: str = 'daily', mode: str = 'trader', use_ai: bool = False, lang: str = 'zh') -> dict:
    """
    Generate a stock report.
    Returns: {title, date_range, sections: [{title, content}], markdown, metadata}
    """
    from db import get_stock_conn

    code = stock_code.zfill(5)
    today = datetime.now()

    # Determine date range
    if report_type == 'daily':
        lookback = 1
        title_suffix = '日报'
    elif report_type == 'weekly':
        lookback = 7
        title_suffix = '周报'
    else:
        lookback = 30
        title_suffix = '月报'

    start_date = (today - timedelta(days=int(lookback * 1.6))).strftime('%Y-%m-%d')
    end_date = today.strftime('%Y-%m-%d')

    sections = []
    stock_name = code

    with get_stock_conn(code) as conn:
        # Get stock name
        info_row = conn.execute("SELECT value FROM stock_info WHERE key = 'stock_name'").fetchone()
        if info_row:
            import json
            try:
                stock_name = json.loads(info_row['value'])
            except:
                stock_name = info_row['value']

        # === Section 1: Price Performance ===
        latest_trade = conn.execute(
            "SELECT * FROM daily_trading ORDER BY trade_date DESC LIMIT 1"
        ).fetchone()
        start_trade = conn.execute(
            "SELECT * FROM daily_trading WHERE trade_date <= ? ORDER BY trade_date DESC LIMIT 1",
            (start_date,)
        ).fetchone()

        trades = conn.execute(
            "SELECT * FROM daily_trading WHERE trade_date >= ? ORDER BY trade_date",
            (start_date,)
        ).fetchall()

        price_section = {'title': '一、行情走势', 'content': ''}
        if latest_trade and trades:
            close = latest_trade['close']
            period_return = None
            if start_trade and start_trade['close']:
                period_return = (close - start_trade['close']) / start_trade['close'] * 100

            max_high = max((t['high'] for t in trades if t['high']), default=None)
            min_low = min((t['low'] for t in trades if t['low']), default=None)
            avg_vol = sum((t['volume'] or 0) for t in trades) / len(trades) if trades else 0
            avg_turnover = sum((t['turnover'] or 0) for t in trades) / len(trades) if trades else 0
            total_turnover = sum((t['turnover'] or 0) for t in trades)

            price_section['content'] = (
                f"- 最新收盘价：**HK${close:.2f}**（{latest_trade['trade_date']}）\n"
                f"- 区间{'日' if report_type=='daily' else '周' if report_type=='weekly' else '月'}涨跌幅："
                f"**{'🔴' if (period_return or 0) >= 0 else '🟢'} {period_return:+.2f}%**\n"
                f"- 区间最高：HK${max_high:.2f} / 最低：HK${min_low:.2f}\n"
                f"- 区间日均成交量：{_fmt_shares(int(avg_vol))}\n"
                f"- 区间总成交额：{_fmt_money(total_turnover)}\n"
            )
        sections.append(price_section)

        # === Section 2: CCASS Holdings ===
        latest_ccass = conn.execute(
            "SELECT * FROM ccass_total ORDER BY trade_date DESC LIMIT 1"
        ).fetchone()
        start_ccass = conn.execute(
            "SELECT * FROM ccass_total WHERE trade_date <= ? ORDER BY trade_date DESC LIMIT 1",
            (start_date,)
        ).fetchone()

        ccass_section = {'title': '二、CCASS持仓变动', 'content': ''}
        if latest_ccass:
            lines = [f"- 最新CCASS总持仓：{_fmt_shares(latest_ccass['total_shares'])}（占总股本 {_fmt_issued_pct(latest_ccass['pct_of_issued'])}）"]
            if start_ccass and start_ccass['total_shares']:
                ccass_chg = latest_ccass['total_shares'] - start_ccass['total_shares']
                latest_pct = latest_ccass['pct_of_issued']
                start_pct = start_ccass['pct_of_issued']
                if latest_pct is not None and start_pct is not None:
                    ccass_pct_chg = latest_pct - start_pct
                    lines.append(f"- 区间CCASS持仓变化：{_fmt_shares(ccass_chg)}（{ccass_pct_chg:+.2f}个百分点）")
                else:
                    lines.append(f"- 区间CCASS持仓变化：{_fmt_shares(ccass_chg)}")

            # Top movers
            latest_date = latest_ccass['trade_date']
            top_movers = conn.execute("""
                SELECT cdc.*, sa.shareholder_name
                FROM ccass_daily_changes cdc
                LEFT JOIN shareholder_attribution sa ON cdc.participant_id = sa.participant_id
                WHERE cdc.trade_date = ?
                ORDER BY ABS(cdc.shares_change) DESC LIMIT 5
            """, (latest_date,)).fetchall()

            if top_movers:
                lines.append(f"\n**最新日席位变动 Top 5：**")
                for m in top_movers:
                    if not m['shares_change']:
                        continue
                    direction = '↑' if m['shares_change'] > 0 else '↓'
                    label = f"{m['participant_name']}"
                    if m['shareholder_name']:
                        label += f"（{m['shareholder_name']}）"
                    lines.append(f"- {direction} {label}：{_fmt_shares(m['shares_change'])}")
            ccass_section['content'] = '\n'.join(lines)
        else:
            ccass_section['content'] = '- CCASS数据暂缺'
        sections.append(ccass_section)

        # === Section 3: Southbound Connect ===
        latest_hk = conn.execute(
            "SELECT * FROM hk_connect ORDER BY trade_date DESC LIMIT 1"
        ).fetchone()
        hk_section = {'title': '三、南向资金', 'content': ''}
        if latest_hk:
            lines = [f"- 最新南向持股：{_fmt_shares(latest_hk['shares'])}（占总股本 {_fmt_issued_pct(latest_hk['pct_of_issued'])}）"]
            # Period southbound change
            hk_series = conn.execute(
                "SELECT * FROM hk_connect WHERE trade_date >= ? ORDER BY trade_date",
                (start_date,)
            ).fetchall()
            if hk_series and len(hk_series) > 1:
                start_hk = hk_series[0]
                end_hk = hk_series[-1]
                hk_period_chg = (end_hk['shares'] or 0) - (start_hk['shares'] or 0)
                lines.append(f"- 区间南向累计{('净买入' if hk_period_chg >= 0 else '净卖出')}：{_fmt_shares(abs(hk_period_chg))}")

                # Sum daily changes
                total_buy = sum((r['shares_change'] or 0) for r in hk_series if (r['shares_change'] or 0) > 0)
                total_sell = abs(sum((r['shares_change'] or 0) for r in hk_series if (r['shares_change'] or 0) < 0))
                lines.append(f"  - 区间总买入：{_fmt_shares(total_buy)}")
                lines.append(f"  - 区间总卖出：{_fmt_shares(total_sell)}")
            hk_section['content'] = '\n'.join(lines)
        else:
            hk_section['content'] = '- 南向数据暂缺'
        sections.append(hk_section)

        # === Section 4: Signal Summary ===
        from services.anomaly_detector import get_signal_score
        signals = get_signal_score(code, latest_ccass['trade_date'] if latest_ccass else None)
        sig_section = {'title': '四、异动信号', 'content': ''}
        if signals:
            lines = [
                f"- 综合评分：**{signals['score']}/100** — {signals['verdict']}",
                f"  - 卖出信号：{signals.get('sell_signals', 0)}个 / 买入信号：{signals.get('buy_signals', 0)}个",
            ]
            if signals.get('anomalies'):
                lines.append("\n**关键异动：**")
                for a in signals['anomalies'][:5]:
                    icon = '⚠️' if a['severity'] == 'high' else '⚡'
                    lines.append(f"- {icon} {a['message']}")
            sig_section['content'] = '\n'.join(lines)
        sections.append(sig_section)

        # === Section 5: Announcements ===
        ann_section = {'title': '五、近期公告', 'content': ''}
        anns = conn.execute(
            "SELECT * FROM announcements WHERE announce_date >= ? ORDER BY announce_date DESC LIMIT 10",
            (start_date,)
        ).fetchall()
        if anns:
            lines = []
            for a in anns:
                cat = f"[{a['category']}]" if a['category'] else ''
                lines.append(f"- **{a['announce_date']}** {cat} {a['title']}")
            ann_section['content'] = '\n'.join(lines)
        else:
            ann_section['content'] = '- 暂无公告数据，可在行情页点击"抓取公告"获取'
        sections.append(ann_section)

        # === IR-only sections ===
        if mode == 'ir':
            # Section: Shareholder Holdings & Selloff
            from services.selloff_engine import get_shareholder_summary
            sh_summary = get_shareholder_summary(code)

            ir_section = {'title': '六、老股东减持追踪（IR）', 'content': ''}
            if sh_summary:
                lines = []
                for sh in sh_summary:
                    baseline = sh['shares_baseline'] or 0
                    current = sh['shares_current'] or 0
                    chg = sh['change_from_baseline'] or 0
                    chg_30d = sh.get('change_30d') or 0

                    if baseline > 0 and current > 0:
                        direction = '减持' if chg < 0 else ('增持' if chg > 0 else '持平')
                        pct = chg / baseline * 100 if baseline else 0
                        lines.append(
                            f"- **{sh['shareholder_name']}**（{sh['participant_name']}，{sh['investor_type'] or '股东'}）：\n"
                            f"  - 基线持股：{_fmt_shares(baseline)}（成本HK${sh['cost_hkd']:.2f}，解禁{sh['unlock_date']}）\n"
                            f"  - 最新持仓：{_fmt_shares(current)}\n"
                            f"  - 较基线{direction}：{_fmt_shares(abs(chg))}（{pct:+.1f}%）"
                        )
                        if chg_30d != 0:
                            lines.append(f"  - 近30日{'减持' if chg_30d < 0 else '增持'}：{_fmt_shares(abs(chg_30d))}")
                ir_section['content'] = '\n'.join(lines) if lines else '- 区间内老股东无明显变动'
            else:
                ir_section['content'] = '- 尚未配置股东归因，请在IR设置中上传股东名册或手动添加股东席位映射'
            sections.append(ir_section)

            # Section: Unlock Calendar
            upcoming = conn.execute("""
                SELECT * FROM unlock_calendar WHERE unlock_date >= date('now') ORDER BY unlock_date LIMIT 5
            """).fetchall()
            unlock_section = {'title': '七、解禁日历（IR）', 'content': ''}
            if upcoming:
                lines = []
                for u in upcoming:
                    cost_str = f"@HK${u['cost_hkd']:.2f}" if u['cost_hkd'] else ''
                    lines.append(f"- **{u['unlock_date']}** {u['shareholder_name']}：{_fmt_shares(u['shares'])} {cost_str}")
                unlock_section['content'] = '\n'.join(lines)
            else:
                unlock_section['content'] = '- 未来3个月无已记录解禁事件'
            sections.append(unlock_section)

        # === Conclusion ===
        conclusion = {'title': '结论', 'content': ''}
        score = signals.get('score', 50) if signals else 50
        if score >= 70:
            verdict = '⚠️ 当前CCASS席位显示较强减持信号，建议关注主要席位资金流向。'
        elif score >= 55:
            verdict = '📉 存在一定减持压力，关注后续席位变动。'
        elif score <= 30:
            verdict = '🟢 席位资金呈现吸筹迹象，可关注后续买入信号确认。'
        elif score <= 45:
            verdict = '📈 有轻微资金流入迹象，持续观察。'
        else:
            verdict = '⚖️ 多空力量相对均衡，暂无明确方向性信号。'
        conclusion['content'] = verdict + '\n\n---\n*本报告基于公开CCASS数据与行情数据自动生成，仅供参考，不构成投资建议。*'
        if mode == 'ir':
            conclusion['content'] += '\n*IR模式报告包含股东归因数据，归因结果基于席位映射，可能存在误差。*'
        sections.append(conclusion)

    # Build markdown
    date_range_str = f"{start_date} 至 {end_date}"
    title = f"{stock_name}（{code}.HK）{title_suffix}"

    md_lines = [f"# {title}\n", f"**报告期间：{date_range_str}**\n", f"**生成时间：{today.strftime('%Y-%m-%d %H:%M')}**\n", f"**报告类型：{'交易者版' if mode == 'trader' else 'IR版'}**\n"]
    for s in sections:
        md_lines.append(f"\n## {s['title']}\n")
        md_lines.append(s['content'] + '\n')

    markdown = '\n'.join(md_lines)

    ai_generated = False
    # Optional AI-enhanced report. If the LLM call fails for any reason, keep the
    # template-based markdown above as a safe fallback.
    if use_ai:
        try:
            from services.llm_service import is_llm_enabled, generate_ai_report
            if is_llm_enabled():
                raw_data = _collect_report_data(code, start_date, mode)
                ai_markdown = generate_ai_report(code, stock_name, report_type, mode, raw_data, lang=lang)
                if ai_markdown:
                    markdown = ai_markdown
                    sections = [{'title': 'AI Enhanced Analysis' if lang == 'en' else 'AI增强分析', 'content': ai_markdown}]
                    ai_generated = True
        except Exception as e:
            logger.error(f"AI report generation failed, falling back to template: {e}")

    return {
        'title': title,
        'stock_code': code,
        'stock_name': stock_name,
        'report_type': report_type,
        'mode': mode,
        'date_range': date_range_str,
        'generated_at': today.strftime('%Y-%m-%d %H:%M'),
        'sections': sections,
        'markdown': markdown,
        'score': signals.get('score') if signals else None,
        'ai_generated': ai_generated,
    }


def _row_to_dict(row):
    return dict(row) if row else None


def _rows_to_dicts(rows):
    return [dict(r) for r in rows] if rows else []


def _collect_report_data(stock_code: str, start_date: str, mode: str = 'trader') -> dict:
    """Collect raw data for LLM-enhanced report generation."""
    from db import get_stock_conn
    from services.anomaly_detector import get_signal_score

    data = {'stock_code': stock_code, 'mode': mode, 'start_date': start_date}
    with get_stock_conn(stock_code) as conn:
        latest_ccass = conn.execute("SELECT * FROM ccass_total ORDER BY trade_date DESC LIMIT 1").fetchone()
        data['latest_trading'] = _row_to_dict(conn.execute("SELECT * FROM daily_trading ORDER BY trade_date DESC LIMIT 1").fetchone())
        data['trading_series'] = _rows_to_dicts(conn.execute(
            "SELECT * FROM daily_trading WHERE trade_date >= ? ORDER BY trade_date", (start_date,)
        ).fetchall())
        data['latest_ccass'] = _row_to_dict(latest_ccass)
        data['ccass_series'] = _rows_to_dicts(conn.execute(
            "SELECT * FROM ccass_total WHERE trade_date >= ? ORDER BY trade_date", (start_date,)
        ).fetchall())
        latest_date = latest_ccass['trade_date'] if latest_ccass else None
        if latest_date:
            data['top_ccass_changes'] = _rows_to_dicts(conn.execute("""
                SELECT cdc.*, sa.shareholder_name
                FROM ccass_daily_changes cdc
                LEFT JOIN shareholder_attribution sa ON cdc.participant_id = sa.participant_id
                WHERE cdc.trade_date = ?
                ORDER BY ABS(cdc.shares_change) DESC LIMIT 20
            """, (latest_date,)).fetchall())
        else:
            data['top_ccass_changes'] = []
        data['southbound_series'] = _rows_to_dicts(conn.execute(
            "SELECT * FROM hk_connect WHERE trade_date >= ? ORDER BY trade_date", (start_date,)
        ).fetchall())
        data['announcements'] = _rows_to_dicts(conn.execute(
            "SELECT * FROM announcements WHERE announce_date >= ? ORDER BY announce_date DESC LIMIT 20", (start_date,)
        ).fetchall())

        data['signals'] = get_signal_score(stock_code, latest_date)

        if mode == 'ir':
            from services.selloff_engine import get_shareholder_summary
            data['shareholders'] = get_shareholder_summary(stock_code)
            data['selloff_recent'] = _rows_to_dicts(conn.execute("""
                SELECT ss.*, dt.close
                FROM shareholder_selloff ss
                LEFT JOIN daily_trading dt ON ss.trade_date = dt.trade_date
                WHERE ss.trade_date >= ?
                ORDER BY ss.trade_date DESC, ABS(ss.shares_change) DESC
                LIMIT 100
            """, (start_date,)).fetchall())
            data['unlock_calendar'] = _rows_to_dicts(conn.execute("""
                SELECT * FROM unlock_calendar WHERE unlock_date >= date('now') ORDER BY unlock_date LIMIT 20
            """).fetchall())
    return data


def _fmt_shares(n):
    if n is None:
        return '-'
    if abs(n) >= 1e8:
        return f"{n/1e8:.2f}亿股"
    if abs(n) >= 1e4:
        return f"{n/1e4:.0f}万股"
    return f"{n:,}股"


def _fmt_money(n):
    if n is None:
        return '-'
    if abs(n) >= 1e8:
        return f"HK${n/1e8:.2f}亿"
    if abs(n) >= 1e4:
        return f"HK${n/1e4:.0f}万"
    return f"HK${n:,.0f}"
