"""
LLM Service — OpenAI-compatible chat completion for AI-enhanced reports.
Reads config (api_key, base_url, model, enabled) and makes API calls.
Falls back gracefully if the API fails.
"""
import json
import logging
from typing import Optional

import httpx

from services.config_service import load_config

logger = logging.getLogger(__name__)


def is_llm_enabled() -> bool:
    """Check if LLM is properly configured and enabled."""
    cfg = load_config()
    llm = cfg.get('llm', {})
    return (
        llm.get('enabled', False)
        and bool(llm.get('api_key'))
        and llm.get('api_key') != '****'
        and bool(llm.get('model'))
        and bool(llm.get('base_url'))
    )


def generate_ai_report(
    stock_code: str,
    stock_name: str,
    report_type: str,
    mode: str,
    data: dict,
    lang: str = 'zh',
) -> Optional[str]:
    """
    Call LLM to generate an enhanced analysis report in Markdown.

    Args:
        stock_code: e.g. '00700'
        stock_name: e.g. '腾讯控股'
        report_type: 'daily' | 'weekly' | 'monthly'
        mode: 'trader' | 'ir'
        data: dict with raw analysis data assembled in report_generator
        lang: 'zh' or 'en' — LLM writes in the same language

    Returns:
        Markdown string or None if the call fails.
    """
    cfg = load_config()
    llm_cfg = cfg.get('llm', {})

    api_key = llm_cfg.get('api_key', '')
    base_url = llm_cfg.get('base_url', 'https://api.openai.com/v1').rstrip('/')
    model = llm_cfg.get('model', 'gpt-4o-mini')
    timeout = float(llm_cfg.get('timeout', 60))

    if not api_key or api_key == '****':
        logger.warning("LLM API key not configured")
        return None

    # Build prompt based on language
    is_english = (lang == 'en')

    # Get RAG context
    from services.rag_service import get_rag_context, init_knowledge_base
    try:
        init_knowledge_base()
        rag_context = get_rag_context(
            f"{stock_name} {report_type} {mode} CCASS selloff cost analysis",
            report_type=report_type, mode=mode
        )
    except Exception as e:
        logger.warning(f"RAG context retrieval failed: {e}")
        rag_context = ""

    system_prompt = (
        "You are a professional Hong Kong stock market analyst specializing in CCASS position analysis, "
        "shareholder selloff tracking, and capital flow interpretation. "
        "You will be given raw data about a HK-listed stock including price, CCASS positions, "
        "Southbound Connect flows, anomaly signals, and announcements. "
        "If IR mode data is provided, you will also receive shareholder cost structure and selloff data. "
        "Write an objective, data-driven analysis in structured Markdown format. "
        "Always cite specific numbers (shares, percentages, amounts) from the data. "
        "Do NOT give definitive buy/sell recommendations. Present analysis objectively. "
        "Keep your response concise — under 2000 Chinese characters or 1500 English words. "
    )

    if rag_context:
        system_prompt += "\n\n" + rag_context

    if is_english:
        system_prompt += "Write your entire response in English."
    else:
        system_prompt += "请使用简体中文撰写全部内容。"

    # Build user message with data
    report_type_label = {'daily': 'Daily', 'weekly': 'Weekly', 'monthly': 'Monthly'}.get(report_type, report_type)
    if not is_english:
        report_type_label = {'daily': '日度', 'weekly': '周度', 'monthly': '月度'}.get(report_type, report_type)

    mode_label = 'Trader View (public data)' if mode == 'trader' else 'IR View (with shareholder data)'
    if not is_english:
        mode_label = '交易者版（公开数据）' if mode == 'trader' else 'IR版（含股东减持数据）'

    # Serialize data for prompt (keep it structured but concise)
    data_summary = json.dumps(data, ensure_ascii=is_english, indent=2, default=str)

    if is_english:
        user_prompt = f"""## Stock: {stock_name} ({stock_code}.HK)
## Report Type: {report_type_label}
## Mode: {mode_label}

### Raw Data:
```json
{data_summary}
```

### Instructions:
Write a {report_type_label} report in Markdown with these sections:

1. **Executive Summary** — Brief overview of key findings (2-3 sentences)
2. **Price Action** — Analyze price trend, volume patterns, key levels
3. **CCASS Position Analysis** — Analyze major participant changes, unusual flows
4. **Southbound Connect** — Analyze northbound/southbound capital flows
5. **Anomaly Signals** — Highlight detected anomalies and their significance
6. **Key Announcements** — Summarize material announcements and their impact"""

        if mode == 'ir':
            user_prompt += """
7. **Shareholder Selloff Analysis** — Analyze shareholder selling patterns, pace, and potential pressure
8. **Unlock Calendar** — Upcoming unlocks and their potential impact"""

        user_prompt += """
9. **Risk Assessment** — Identify key risks and watch points

Use **bold** for key numbers. Use 🔴 for bearish signals and 🟢 for bullish signals.
Be specific with numbers and percentages from the data.
Do not give buy/sell advice.
"""
    else:
        user_prompt = f"""## 股票：{stock_name}（{stock_code}.HK）
## 报告类型：{report_type_label}
## 报告模式：{mode_label}

### 原始数据：
```json
{data_summary}
```

### 写作要求：
请生成一份{report_type_label}分析报告，使用Markdown格式，包含以下章节：

1. **摘要** — 核心发现概述（2-3句话）
2. **行情走势分析** — 价格趋势、成交量模式、关键价位
3. **CCASS持仓变动分析** — 主要席位变动、异常资金流向
4. **南向资金分析** — 南北向资金流向解读
5. **异动信号** — 检测到的异常信号及其重要性
6. **重要公告** — 重大公告梳理及影响"""

        if mode == 'ir':
            user_prompt += """
7. **老股东减持分析** — 股东减持节奏、力度、潜在抛压分析
8. **解禁日历** — 即将到来的解禁及其潜在影响"""

        user_prompt += """
9. **风险提示** — 关键风险点和需要关注的事项

关键数字请用**加粗**标注。利空信号用🔴，利好信号用🟢。
请引用具体数字和百分比。
不给出明确的买卖建议，保持客观分析立场。
"""

    # Call OpenAI-compatible API
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 3000,
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            result = resp.json()

        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            logger.error("LLM returned empty content")
            return None

        logger.info(f"LLM report generated successfully for {stock_code}, model={model}, tokens={result.get('usage', {})}")
        return content.strip()

    except httpx.HTTPStatusError as e:
        logger.error(f"LLM API error: {e.response.status_code} - {e.response.text[:500]}")
        return None
    except httpx.RequestError as e:
        logger.error(f"LLM request error: {e}")
        return None
    except Exception as e:
        logger.error(f"LLM unexpected error: {e}")
        return None
