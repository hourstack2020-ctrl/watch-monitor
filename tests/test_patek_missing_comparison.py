import unittest
import app


class PatekComparisonTests(unittest.TestCase):
    def rows(self):
        return [dict(site=site,url=site,title=title,price=price,missing_runs=0)
                for site,title,price in [
                    ('永生','Patek Philippe 百達翡麗 PP錶 Nautilus 5980/1R 金鷹 5980/1R-001 18K玫瑰金材質 鍊帶款 同軸計時碼表 2023年保單',7088000),
                    ('鐘點站','Patek Philippe 5980/1R-001 2020年保卡',6488000)]]

    def test_full_reference_after_short_reference(self):
        self.assertEqual(app.model_of(self.rows()[0]['title']),'5980/1R-001')
        self.assertEqual(app.model_of('Patek Philippe 5980/1R'),'5980/1R')

    def test_missing_dial_is_displayed_pending(self):
        result=app.same_product_items(self.rows(),{}, {})
        self.assertEqual(len(result['groups']),1)
        group=result['groups'][0]
        self.assertEqual(group['listing_count'],2)
        self.assertEqual(group['spread'],600000)
        self.assertEqual(group['unverified_count'],1)
        self.assertTrue(all('面盤文字資料不足' in r['comparison_note'] for r in group['listings']))
        self.assertEqual(len(app.image_comparison_candidates(self.rows())),2)

    def test_different_suffix_does_not_merge(self):
        rows=self.rows()
        rows[1]['title']=rows[1]['title'].replace('-001','-010')
        self.assertEqual(app.same_product_items(rows,{}, {})['groups'],[])

    def test_unknown_dial_does_not_bridge_distinct_dials(self):
        rows=self.rows()
        rows[0]['title']+=' 黑色面盤 黑色小錶盤'
        rows[1]['title']+=' 白色面盤 白色小錶盤'
        rows.append(dict(rows[0],url='unknown',title='Patek Philippe 5980/1R-001'))
        self.assertEqual(app.same_product_items(rows,{}, {})['groups'],[])
