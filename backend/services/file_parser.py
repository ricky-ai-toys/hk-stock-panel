"""
File parser for IR onboarding.
Supports Excel (.xlsx), CSV, PDF for shareholder/broker mapping uploads.
"""
import os
import logging
import json
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def parse_number(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val) if isinstance(val, int) or val == int(val) else float(val)
    s = str(val).strip().replace(',', '').replace(' ', '').replace('股', '')
    if not s or s in ('-', 'N/A', 'n/a', '—'):
        return None
    try:
        f = float(s)
        return int(f) if f == int(f) else f
    except (ValueError, TypeError):
        return None


def detect_file_type(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in ('.xlsx', '.xls'):
        return 'excel'
    elif ext == '.csv':
        return 'csv'
    elif ext == '.pdf':
        return 'pdf'
    elif ext in ('.txt', '.tsv'):
        return 'text'
    return 'unknown'


def parse_excel(filepath: str) -> list[dict]:
    """Parse Excel file and return list of row dicts."""
    import openpyxl
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    all_rows = []
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        # Try to find header row
        header_idx = _find_header_row(rows)
        if header_idx is None:
            continue
        headers = [str(h).strip() if h else f'col_{i}' for i, h in enumerate(rows[header_idx])]
        for row in rows[header_idx + 1:]:
            if not any(c is not None for c in row):
                continue
            record = {}
            for i, h in enumerate(headers):
                if i < len(row):
                    record[h] = row[i]
            all_rows.append(record)
    wb.close()
    return all_rows


def parse_csv(filepath: str) -> list[dict]:
    """Parse CSV file."""
    import csv
    rows = []
    # Try UTF-8 then GBK
    for encoding in ['utf-8-sig', 'gbk', 'gb2312', 'utf-8']:
        try:
            with open(filepath, 'r', encoding=encoding) as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    return [{k.strip(): v for k, v in r.items()} for r in rows]


def parse_pdf(filepath: str) -> list[dict]:
    """Parse PDF tables using pdfplumber."""
    import pdfplumber
    all_rows = []
    try:
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if not table or len(table) < 2:
                        continue
                    header_idx = _find_header_row(table)
                    if header_idx is None:
                        continue
                    headers = [str(h).strip() if h else f'col_{i}' for i, h in enumerate(table[header_idx])]
                    for row in table[header_idx + 1:]:
                        if not any(c for c in row):
                            continue
                        record = {}
                        for i, h in enumerate(headers):
                            record[h] = row[i] if i < len(row) else None
                        all_rows.append(record)
    except Exception as e:
        logger.error(f"PDF parse error: {e}")
    return all_rows


def _find_header_row(rows: list) -> Optional[int]:
    """Heuristic to find the header row in a table."""
    keywords = {'股东', 'shareholder', '券商', 'broker', '席位', 'participant', '持股', 'shares',
                '开户', '银行', '解禁', 'unlock', '名称', 'name', '编号', 'id', '代码', 'code'}
    for i, row in enumerate(rows[:5]):
        if not row:
            continue
        text = ' '.join(str(c).lower() for c in row if c is not None)
        score = sum(1 for kw in keywords if kw in text)
        if score >= 2:
            return i
    return 0 if rows and any(c for c in rows[0]) else None


# 股东/券商字段映射 - 常见列名到标准字段
FIELD_ALIASES = {
    'shareholder_name': ['股东', '股东名称', '股东姓名', '投资者名称', 'shareholder', 'investor', 'name', '名称'],
    'participant_id': ['席位号', '参与者编号', '券商编号', 'ccass编号', 'participant_id', 'pid', 'broker_id', '编号', '代码', 'id'],
    'participant_name': ['券商', '席位', '开户银行', '开户行', '托管券商', 'participant', 'broker', 'custodian', '席位名称'],
    'shares': ['持股数', '持股数量', '持股', '股数', '数量', 'shares', 'holding', '持股量'],
    'investor_type': ['类型', '股东类型', '投资者类型', 'type', 'category', '股份类型'],
    'cost_hkd': ['成本', '入股价', '投资成本', '发行价', 'cost', 'price', 'ipo价格'],
    'unlock_date': ['解禁日', '解禁日期', '解锁日', '锁定期', 'unlock', 'lockup_expiry', '解禁时间'],
}


def map_fields(record: dict) -> dict:
    """Map column aliases to standard field names."""
    mapped = {}
    for std_field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            for key, value in record.items():
                key_str = str(key).strip().lower()
                if alias.lower() in key_str and value is not None and str(value).strip():
                    mapped[std_field] = value
                    break
            if std_field in mapped:
                break
    return mapped


def parse_uploaded_file(filepath: str, original_filename: str) -> dict:
    """
    Parse an uploaded file and extract shareholder/broker mapping data.
    Returns: {
        'file_type': str,
        'rows_raw': list[dict],    # raw rows
        'attributions': list[dict], # mapped shareholder attributions
        'unlocks': list[dict],      # unlock calendar entries
        'summary': dict,            # parsing summary
    }
    """
    ftype = detect_file_type(original_filename)

    if ftype == 'excel':
        raw_rows = parse_excel(filepath)
    elif ftype == 'csv':
        raw_rows = parse_csv(filepath)
    elif ftype == 'pdf':
        raw_rows = parse_pdf(filepath)
    else:
        return {'file_type': ftype, 'error': f'Unsupported file type: {ftype}', 'rows_raw': [], 'attributions': [], 'unlocks': [], 'summary': {}}

    attributions = []
    unlocks = []

    for row in raw_rows:
        mapped = map_fields(row)
        if mapped.get('shareholder_name') or mapped.get('participant_name'):
            # Clean up
            attr = {
                'shareholder_name': str(mapped.get('shareholder_name', '')).strip(),
                'participant_id': str(mapped.get('participant_id', '')).strip().upper() if mapped.get('participant_id') else '',
                'participant_name': str(mapped.get('participant_name', '')).strip(),
                'shares_baseline': parse_number(mapped.get('shares')),
                'investor_type': str(mapped.get('investor_type', '')).strip() if mapped.get('investor_type') else '',
                'cost_hkd': parse_number(mapped.get('cost_hkd')),
                'unlock_date': str(mapped.get('unlock_date', '')).strip()[:10] if mapped.get('unlock_date') else None,
            }
            if attr['shareholder_name']:
                attributions.append(attr)

            # Check for unlock date
            if attr.get('unlock_date') and attr.get('shares_baseline'):
                unlocks.append({
                    'unlock_date': attr['unlock_date'],
                    'shareholder_name': attr['shareholder_name'],
                    'shares': attr['shares_baseline'],
                    'cost_hkd': attr['cost_hkd'],
                    'broker': attr['participant_name'],
                    'investor_type': attr['investor_type'],
                })

    summary = {
        'total_rows': len(raw_rows),
        'attributions_found': len(attributions),
        'unlocks_found': len(unlocks),
        'unique_shareholders': len(set(a['shareholder_name'] for a in attributions)),
        'unique_seats': len(set(a['participant_id'] for a in attributions if a['participant_id'])),
    }

    logger.info(f"Parsed {original_filename}: {summary}")
    return {
        'file_type': ftype,
        'rows_raw': raw_rows,
        'attributions': attributions,
        'unlocks': unlocks,
        'summary': summary,
    }


def apply_attributions(stock_code: str, attributions: list[dict], unlocks: list[dict]):
    """Save parsed attributions and unlock data to stock DB."""
    from db import get_stock_conn
    code = stock_code.zfill(5)
    with get_stock_conn(code) as conn:
        for a in attributions:
            conn.execute("""
                INSERT OR REPLACE INTO shareholder_attribution
                (shareholder_name, participant_id, participant_name, shares_baseline,
                 investor_type, cost_hkd, unlock_date, attribution_type, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'upload', 'high')
            """, (
                a.get('shareholder_name', ''),
                a.get('participant_id', ''),
                a.get('participant_name', ''),
                a.get('shares_baseline', 0),
                a.get('investor_type', ''),
                a.get('cost_hkd'),
                a.get('unlock_date'),
            ))

        for u in unlocks:
            conn.execute("""
                INSERT OR REPLACE INTO unlock_calendar
                (unlock_date, shareholder_name, shares, cost_hkd, broker, investor_type, unlock_status)
                VALUES (?, ?, ?, ?, ?, ?, 'upcoming')
            """, (
                u.get('unlock_date'),
                u.get('shareholder_name', ''),
                u.get('shares', 0),
                u.get('cost_hkd'),
                u.get('broker', ''),
                u.get('investor_type', ''),
            ))


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2:
        print("Usage: python file_parser.py <filepath>")
        sys.exit(1)
    result = parse_uploaded_file(sys.argv[1], os.path.basename(sys.argv[1]))
    print(json.dumps(result['summary'], indent=2, ensure_ascii=False))
    print(f"\nAttributions: {len(result['attributions'])}")
    for a in result['attributions'][:5]:
        print(f"  {a}")
