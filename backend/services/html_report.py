"""
HTML Report Renderer — generates standalone HTML reports with inline charts.
Uses inline SVG charts (no external JS dependencies in the output file).
"""
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def render_html_report(report_data: dict) -> str:
    """Render report data as a standalone HTML page with embedded SVG charts."""
    code = report_data['stock_code']
    name = report_data.get('stock_name', code)
    title = report_data['title']
    mode = report_data.get('mode', 'trader')
    date_range = report_data.get('date_range', '')
    generated_at = report_data.get('generated_at', '')
    score = report_data.get('score')
    sections = report_data.get('sections', [])

    # Extract price data for chart from section content
    price_chart_svg = _render_price_chart_placeholder()
    ccass_chart_svg = _render_ccass_chart_placeholder()

    score_color = _score_color(score)
    score_label = _score_label(score)

    mode_badge = '📈 交易者版' if mode == 'trader' else '🏢 IR版'

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; color: #1e293b; background: #f8fafc; line-height: 1.7; }}
.container {{ max-width: 860px; margin: 0 auto; padding: 24px 16px; }}
.header {{ background: linear-gradient(135deg, #1e293b 0%, #1e40af 100%); color: white; padding: 40px 32px; border-radius: 16px; margin-bottom: 24px; }}
.header h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 8px; }}
.header .meta {{ font-size: 14px; color: #94a3b8; }}
.header .badges {{ display: flex; gap: 8px; margin-top: 16px; flex-wrap: wrap; }}
.badge {{ display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 500; }}
.badge-blue {{ background: rgba(37,99,235,0.2); color: #93c5fd; }}
.badge-white {{ background: rgba(255,255,255,0.15); color: #e2e8f0; }}
.score-card {{ display: inline-flex; align-items: center; gap: 12px; background: {score_color}15; border: 1px solid {score_color}40; color: {score_color}; padding: 12px 20px; border-radius: 12px; margin: 16px 0; font-weight: 600; }}
.score-card .num {{ font-size: 32px; font-weight: 800; }}
.section {{ background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 24px; margin-bottom: 16px; }}
.section h2 {{ font-size: 18px; font-weight: 700; color: #0f172a; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 2px solid #f1f5f9; }}
.metric-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 16px; }}
.metric {{ background: #f8fafc; border-radius: 8px; padding: 12px 16px; }}
.metric .label {{ font-size: 12px; color: #64748b; margin-bottom: 4px; }}
.metric .value {{ font-size: 20px; font-weight: 700; color: #0f172a; }}
.metric .sub {{ font-size: 12px; margin-top: 2px; }}
.up {{ color: #dc2626; }}
.down {{ color: #16a34a; }}
.neutral {{ color: #64748b; }}
ul {{ list-style: none; padding: 0; }}
li {{ padding: 8px 0; border-bottom: 1px solid #f1f5f9; font-size: 14px; }}
li:last-child {{ border-bottom: none; }}
.conclusion {{ background: linear-gradient(135deg, #f0f9ff 0%, #eff6ff 100%); border: 1px solid #bfdbfe; border-radius: 12px; padding: 20px; margin: 16px 0; font-size: 15px; }}
.disclaimer {{ font-size: 12px; color: #94a3b8; text-align: center; margin-top: 32px; padding: 16px; }}
.chart-container {{ background: #f8fafc; border-radius: 8px; padding: 16px; margin: 12px 0; }}
.chart-title {{ font-size: 13px; color: #64748b; margin-bottom: 8px; }}
svg text {{ font-family: -apple-system, sans-serif; font-size: 10px; fill: #64748b; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>{name}（{code}.HK）</h1>
    <div class="meta">{title.replace(name, '').replace(f'（{code}.HK）', '')} · {date_range}</div>
    <div class="meta">生成时间：{generated_at}</div>
    <div class="badges">
      <span class="badge badge-blue">{mode_badge}</span>
      <span class="badge badge-white">{date_range}</span>
    </div>
  </div>
"""

    # Score card
    if score is not None:
        html += f"""
  <div class="score-card">
    <span class="num">{score}</span>
    <span>/100 {score_label}</span>
  </div>
"""

    # Render sections
    for i, section in enumerate(sections):
        title_s = section.get('title', '')
        content = section.get('content', '')

        if title_s == '结论':
            html += f'<div class="conclusion">{_format_content(content)}</div>'
            continue

        html += f'<div class="section"><h2>{_escape(title_s)}</h2>'
        html += _format_content(content)

        # Add placeholder charts for key sections
        if '行情' in title_s:
            html += '<div class="chart-container"><div class="chart-title">📊 股价走势（示意）</div>'
            html += price_chart_svg
            html += '</div>'
        elif 'CCASS' in title_s:
            html += '<div class="chart-container"><div class="chart-title">🏦 CCASS席位集中度</div>'
            html += ccass_chart_svg
            html += '</div>'

        html += '</div>'

    html += f"""
  <div class="disclaimer">
    <p>本报告基于公开CCASS数据与行情数据自动生成，仅供参考，不构成投资建议。</p>
    <p>数据来源：HKEX披露易 · 腾讯财经 · Yahoo Finance</p>
    <p style="margin-top:8px;">Generated by HK Stock Panel · {generated_at}</p>
  </div>
</div>
</body>
</html>"""
    return html


def _format_content(content: str) -> str:
    """Convert markdown-like content to HTML."""
    import re
    lines = content.split('\n')
    html_parts = []
    in_list = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            continue
        if stripped.startswith('- '):
            if not in_list:
                html_parts.append('<ul>')
                in_list = True
            item = stripped[2:]
            item = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', item)
            # Color indicators
            item = item.replace('🔴', '<span class="up">🔴</span>')
            item = item.replace('🟢', '<span class="down">🟢</span>')
            html_parts.append(f'<li>{item}</li>')
        elif stripped.startswith('**') and stripped.endswith('**'):
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            html_parts.append(f'<p><strong>{_escape(stripped[2:-2])}</strong></p>')
        elif stripped.startswith('---'):
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            html_parts.append('<hr style="border:none;border-top:1px solid #e2e8f0;margin:12px 0;">')
        else:
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            formatted = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', _escape(stripped))
            formatted = f'<p style="font-size:14px;margin:4px 0;">{formatted}</p>'
            formatted = formatted.replace('🔴', '<span class="up">🔴</span>')
            formatted = formatted.replace('🟢', '<span class="down">🟢</span>')
            html_parts.append(formatted)
    if in_list:
        html_parts.append('</ul>')
    return '\n'.join(html_parts)


def _render_price_chart_placeholder() -> str:
    return '<svg width="100%" height="180" viewBox="0 0 800 180"><line x1="40" y1="140" x2="780" y2="140" stroke="#e2e8f0"/><line x1="40" y1="20" x2="40" y2="140" stroke="#e2e8f0"/><text x="40" y="155">价格走势将在完整版中显示</text><polyline points="80,120 140,100 200,110 260,80 320,90 380,60 440,70 500,50 560,65 620,40 680,55 740,35" fill="none" stroke="#2563eb" stroke-width="2"/><circle cx="740" cy="35" r="4" fill="#2563eb"/></svg>'


def _render_ccass_chart_placeholder() -> str:
    return '<svg width="100%" height="120" viewBox="0 0 800 120"><text x="40" y="60" fill="#94a3b8">席位分布图表将在完整版中显示</text><rect x="80" y="20" width="80" height="80" fill="#2563eb" opacity="0.8"/><rect x="180" y="40" width="80" height="60" fill="#3b82f6" opacity="0.7"/><rect x="280" y="55" width="80" height="45" fill="#60a5fa" opacity="0.6"/><rect x="380" y="65" width="80" height="35" fill="#93c5fd" opacity="0.5"/><rect x="480" y="75" width="80" height="25" fill="#bfdbfe" opacity="0.4"/></svg>'


def _score_color(score):
    if score is None: return '#64748b'
    if score >= 70: return '#dc2626'
    if score >= 55: return '#ea580c'
    if score <= 30: return '#16a34a'
    if score <= 45: return '#2563eb'
    return '#ca8a04'


def _score_label(score):
    if score is None: return ''
    if score >= 70: return '减持信号强'
    if score >= 55: return '有减持压力'
    if score <= 30: return '吸筹信号强'
    if score <= 45: return '资金流入'
    return '多空均衡'


def _escape(s: str) -> str:
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
