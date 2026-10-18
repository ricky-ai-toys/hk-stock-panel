#!/usr/bin/env python3
"""Example: Seed shareholder attribution rules from a CSV/JSON config.

This script demonstrates how to populate the shareholder_attribution table
for a given stock code. Copy and adapt for your own stocks.

Usage:
    python3 scripts/seed_attributions.py <stock_code> <attributions.json>

See examples/attributions_example.json for the expected JSON format.
"""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from db import get_stock_conn  # noqa: E402
from services.selloff_engine import compute_selloff_range  # noqa: E402


def seed(stock_code: str, shareholders: list):
    with get_stock_conn(stock_code) as conn:
        conn.execute('DELETE FROM shareholder_attribution')
        conn.execute('DELETE FROM shareholder_selloff')
        for s in shareholders:
            conn.execute('''
                INSERT INTO shareholder_attribution
                (shareholder_name, participant_id, participant_name, shares_baseline,
                 investor_type, cost_hkd, unlock_date, attribution_type, confidence, notes,
                 sell_start_date, sell_end_date, rule, static_shares)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'manual', ?, ?, ?, ?, ?, ?)
            ''', (
                s['shareholder_name'], s['participant_id'], s['participant_name'],
                s.get('shares_baseline'), s.get('investor_type'), s.get('cost_hkd'),
                s.get('unlock_date'), s.get('confidence', 'med'), s.get('notes', ''),
                s.get('sell_start_date'), s.get('sell_end_date'),
                s.get('rule', 'all_flow'), s.get('static_shares', 0),
            ))
    results = compute_selloff_range(stock_code, 90)
    print(f'Seeded {len(shareholders)} attribution rows for {stock_code}; '
          f'recomputed {len(results)} selloff rows')


def main():
    if len(sys.argv) < 3:
        print('Usage: python3 seed_attributions.py <stock_code> <attributions.json>')
        print('Example: python3 seed_attributions.py 00700 ../examples/attributions_example.json')
        sys.exit(1)
    stock_code = sys.argv[1]
    config_path = Path(sys.argv[2])
    if not config_path.exists():
        print(f'Config file not found: {config_path}')
        sys.exit(1)
    with open(config_path) as f:
        shareholders = json.load(f)
    seed(stock_code, shareholders)


if __name__ == '__main__':
    main()
