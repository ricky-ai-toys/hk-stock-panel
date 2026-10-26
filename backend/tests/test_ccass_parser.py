"""Parser tests for HKEX CCASS pages that omit % of issued units.

07709 (CSOP SK Hynix Daily Max 2x) is published with shareholdings but without
the percent column, because HKEX has no current issued-units figure. The old
parser required 5 cells and dropped every row, so the panel showed no CCASS data.
"""
import os
import sys
import unittest

from bs4 import BeautifulSoup

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from scrapers.ccass_scraper import _parse_ccass_summary, _parse_participant_rows
from services.report_generator import _fmt_issued_pct


NO_PCT_HTML = """
<div class="ccass-search-datarow ccass-search-total">
  <div class="summary-category">總數</div>
  <div class="shareholding"><div class="header">於中央結算系統的持股量</div><div class="value">1,312,500,000</div></div>
  <div class="number-of-participants"><div class="header">參與者數目</div><div class="value">344</div></div>
  <div class="percent-of-participants"><div class="header">佔已發行股份/權證/單位百分比</div><div class="value"></div></div>
</div>
<table><tr><th>header</th></tr></table>
<table>
  <tr>
    <th>參與者編號</th><th>名稱</th><th>地址</th><th>持股量</th>
  </tr>
  <tr>
    <td class="col-participant-id"><div class="mobile-list-body">B01955</div></td>
    <td class="col-participant-name"><div class="mobile-list-body">富途證券國際(香港)有限公司</div></td>
    <td class="col-address"><div class="mobile-list-body">34/F UNITED CENTRE</div></td>
    <td class="col-shareholding text-right"><div class="mobile-list-body">175,813,892</div></td>
  </tr>
  <tr>
    <td class="col-participant-id"><div class="mobile-list-body">C00019</div></td>
    <td class="col-participant-name"><div class="mobile-list-body">香港上海匯豐銀行有限公司</div></td>
    <td class="col-address"><div class="mobile-list-body">HSBC CENTRE</div></td>
    <td class="col-shareholding text-right"><div class="mobile-list-body">159,593,404</div></td>
  </tr>
</table>
"""

WITH_PCT_HTML = """
<div class="ccass-search-datarow ccass-search-total">
  <div class="shareholding"><div class="value">4,891,154,719</div></div>
  <div class="number-of-participants"><div class="value">993</div></div>
  <div class="percent-of-participants"><div class="value">94.72%</div></div>
</div>
<table>
  <tr>
    <td class="col-participant-id"><div class="mobile-list-body">C00019</div></td>
    <td class="col-participant-name"><div class="mobile-list-body">香港上海匯豐銀行有限公司</div></td>
    <td class="col-address"><div class="mobile-list-body">HSBC CENTRE</div></td>
    <td class="col-shareholding text-right"><div class="mobile-list-body">1,279,043,637</div></td>
    <td class="col-shareholding-percent text-right"><div class="mobile-list-body">24.77%</div></td>
  </tr>
</table>
"""

POSITIONAL_HTML = """
<table><tr><td>ignore</td></tr></table>
<table>
  <tr>
    <td>B01955</td>
    <td>富途證券</td>
    <td>ADMIRALTY</td>
    <td>175,813,892</td>
  </tr>
</table>
"""


class CcassParserTests(unittest.TestCase):
    def test_missing_percent_column_keeps_holdings(self):
        soup = BeautifulSoup(NO_PCT_HTML, 'html.parser')
        summary = _parse_ccass_summary(soup)
        rows = _parse_participant_rows(soup)

        self.assertEqual(summary['total_shares'], 1312500000)
        self.assertIsNone(summary['total_pct'])
        self.assertEqual(summary['participant_count'], 344)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['participant_id'], 'B01955')
        self.assertEqual(rows[0]['shares'], 175813892)
        self.assertIsNone(rows[0]['pct_of_issued'])
        self.assertEqual(rows[1]['participant_name'], '香港上海匯豐銀行有限公司')

    def test_percent_column_still_parsed(self):
        soup = BeautifulSoup(WITH_PCT_HTML, 'html.parser')
        summary = _parse_ccass_summary(soup)
        rows = _parse_participant_rows(soup)

        self.assertEqual(summary['total_shares'], 4891154719)
        self.assertEqual(summary['total_pct'], 94.72)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['shares'], 1279043637)
        self.assertEqual(rows[0]['pct_of_issued'], 24.77)

    def test_positional_fallback_without_percent(self):
        soup = BeautifulSoup(POSITIONAL_HTML, 'html.parser')
        rows = _parse_participant_rows(soup)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['participant_id'], 'B01955')
        self.assertEqual(rows[0]['shares'], 175813892)
        self.assertIsNone(rows[0]['pct_of_issued'])

    def test_report_pct_formatter_accepts_missing_percent(self):
        self.assertEqual(_fmt_issued_pct(None), '未披露')
        self.assertEqual(_fmt_issued_pct(94.72), '94.72%')


if __name__ == '__main__':
    unittest.main()
