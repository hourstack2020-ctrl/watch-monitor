import unittest
from unittest.mock import patch
from pathlib import Path
from bs4 import BeautifulSoup
from app import SITES, brand_of, model_of, extract, listing_event_kind, same_product_items, item_strap, condition_grade
from dial_images import allowed_url
from watchstore_source import SITE, ROOT, parse_inventory, pagination, parse_details, apply_details


def card(pid, title, price):
    return f'''<table width=245><tr><td><a href="prod_detail.asp?prodnum={pid}"><img src="product/{pid}_S.jpg"></a></td></tr>
    <tr><td><table><tr><td><p>{title}</p><p>歡迎來店手錶置換，將以市場最高價收購。</p></td></tr>
    <tr><td>價格：{price}</td></tr><tr><td><a href="prod_detail.asp?prodnum={pid}"><img src="images/detail.jpg"></a></td></tr></table></td></tr></table>'''


def specs(strap='蠔式錶帶', condition='9成5新'):
    return f'''<table><tr><td>錶況：</td><td>全新（其他商品）</td></tr></table>
    <img src="images/iwatch_standard.jpg"><table><tr><td>錶帶：</td><td>{strap}</td><td>原廠保單/錶盒：</td><td>原廠盒單</td></tr>
    <tr><td>錶況：</td><td>{condition}</td><td></td><td></td></tr></table>'''


class WatchStoreTests(unittest.TestCase):
    def parse(self, html):
        return parse_inventory(BeautifulSoup(html, 'html.parser'), ROOT, brand_of, model_of)

    def test_each_image_link_uses_its_own_price_and_skips_accessories(self):
        rows = self.parse(card(1, 'ROLEX GMT-Master II 126711 CHNR 黑色面盤 2019年保單 二手美品', '$548,000')
                          + card(2, 'Patek Philippe 5968R 棕色面盤 2026年保單 未使用品 官網定價：9,000,000', '$4,880,000')
                          + card(3, '正品 勞力士 ROLEX 正版原廠紙袋', '$300'))
        self.assertEqual(len(rows), 2)
        self.assertEqual([r['price'] for r in rows], [548000, 4880000])
        self.assertEqual(rows[0]['model'], '126711CHNR')
        self.assertEqual(rows[0]['year'], '2019')
        self.assertEqual(rows[0]['condition'], '二手美品')
        self.assertEqual(rows[1]['condition'], '未使用品')
        self.assertEqual(rows[0]['image_url'], ROOT + 'product/1_S.jpg')
        self.assertNotIn('歡迎', rows[0]['title'])

    def test_enquiry_has_no_numeric_price_and_sold_is_not_active(self):
        rows = self.parse(card(1, 'ROLEX 126334 灰色面盤 未使用品', '(面洽) (請來電洽詢)')
                          + card(2, 'ROLEX 126334 白色面盤 已售出', '$390,000'))
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]['price'])

    def test_watch_with_unparsed_reference_still_monitored_but_not_compared(self):
        rows = self.parse(card(1, 'Jaeger 積家錶 Master 地理學家 豪華鑲鑽 貝殼面 萬年曆 鬧鈴 自動機芯 40MM 二手美品', '$895,000'))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['model'], '')
        self.assertEqual(same_product_items(rows)['groups'], [])

    def test_broken_page_and_unknown_price_fail_closed(self):
        for html in ['<title>暫時無法使用</title>', card(1, 'ROLEX 126334 黑色面盤', '$abc'),
                     '<a href="prod_detail.asp?prodnum=1"><img src="product/1.jpg"></a>']:
            with self.assertRaises(ValueError):
                self.parse(html)

    def test_last_page_enumerates_all_pages_without_sold_or_filtered_lists(self):
        soup = BeautifulSoup('''<a href="?page=2">2</a><a href="?keywords=&larcode=&newsclass=&page=8">最後頁</a>
            <a href="sold.asp?page=99">99</a><a href="?larcode=A01&page=50">50</a>
            <a href="https://evil.test/?page=100">100</a>''', 'html.parser')
        self.assertEqual(pagination(soup, ROOT), [ROOT + '?page=' + str(p) for p in range(2, 9)])

    def test_source_dispatch_and_first_scan_baseline(self):
        self.assertEqual(SITES[SITE], ROOT)
        class Response:
            apparent_encoding = 'utf-8'
            text = card(1, 'ROLEX 126334 灰色面盤 未使用品', '$390,000')
        detail = Response(); detail.text = specs()
        with patch('app.fetch_page', side_effect=[Response(), detail]), patch('app.time.sleep'):
            rows, _ = extract(SITE, ROOT, None)
        self.assertEqual(rows[0]['site'], SITE)
        self.assertEqual(rows[0]['condition'], '9成5新')
        self.assertIsNone(listing_event_kind(None, True))
        self.assertEqual(listing_event_kind(None, False), 'listed')
        self.assertTrue(allowed_url(rows[0]['image_url']))
        self.assertFalse(allowed_url('https://www.watchstore.tw.evil.test/product/1.jpg'))

    def test_detail_fields_override_title_without_mixing_related_products(self):
        row = self.parse(card(1, 'ROLEX 226627 黑色面盤 2026年保單 二手美品 五株錶帶', '$718,000'))[0]
        fields = parse_details(BeautifulSoup(specs(), 'html.parser'))
        row = apply_details(row, fields)
        self.assertEqual(row['condition'], '9成5新')
        self.assertEqual(condition_grade(row['condition']), '9.5成新')
        self.assertEqual(item_strap(row), '三板蠔式鍊帶')
        self.assertEqual(item_strap(row, normalized=True), '三板蠔式鍊帶')
        self.assertEqual(apply_details(row, fields)['title'], row['title'])

    def test_raw_strap_is_displayed_without_assuming_steel_means_oyster(self):
        row = self.parse(card(1, 'ROLEX 126334 灰色面盤 五株錶帶', '$390,000'))[0]
        row = apply_details(row, {'錶帶': '不鏽鋼錶帶', '錶況': '9成9新'})
        self.assertEqual(item_strap(row), '不鏽鋼錶帶')
        self.assertEqual(item_strap(row, normalized=True), '')
        self.assertEqual(condition_grade(row['condition']), '9.9成新')

    def test_failed_detail_retains_old_record_and_disables_delisting(self):
        class Response:
            apparent_encoding = 'utf-8'
            text = card(1, 'ROLEX 126334 灰色面盤 未使用品', '$390,000')
        with patch('app.fetch_page', side_effect=[Response(), ValueError('detail unavailable')]), patch('app.time.sleep'):
            rows, soup = extract(SITE, ROOT, None)
        self.assertEqual(rows, [])
        self.assertEqual(len(soup.watchstore_errors), 1)
        with self.assertRaises(ValueError):
            parse_details(BeautifulSoup('<td>錶況：9成5新</td>', 'html.parser'))

    def test_new_source_participates_in_existing_comparison_rules(self):
        rows = self.parse(card(1, 'ROLEX 126334 藍色面盤 2026年保單 未使用品', '$390,000'))
        rows.append(dict(rows[0], site='鐘點站', url='clock', price=400000))
        groups = same_product_items(rows)['groups']
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['store_count'], 2)
        self.assertEqual(groups[0]['spread'], 10000)

    def test_store_available_in_monthly_records_and_ui_filters(self):
        import app as backend
        class DB:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def execute(self, *args): return self
            def fetchall(self): return []
        with patch.object(backend, 'connect', return_value=DB()), backend.app.test_request_context('/api/monthly-events?month=2026-10'):
            data = backend.monthly_events.__wrapped__().get_json()
        group = next(x for x in data['groups'] if x['site'] == SITE)
        self.assertEqual(group['counts'], {'listed': 0, 'removed': 0, 'returned': 0})
        html = BeautifulSoup(Path('index.html').read_text(), 'html.parser')
        for control in ('site', 'comparisonSite', 'eventSite'):
            self.assertIn(SITE, html.find(id=control).get_text())


if __name__ == '__main__':
    unittest.main()
