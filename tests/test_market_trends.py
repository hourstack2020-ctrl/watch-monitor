import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from market_trends import normalize, variable

class MarketTest(unittest.TestCase):
    def setUp(self):
        self.row=dict(ST_CODE='one',ST_WEB_NAME='one',ST_ITEMGROUP='PP',ST_NAME='Patek Philippe Nautilus 精鋼 藍色 自動機芯 5811/1G-001 99% 全新',NO_PRICE=800000,NO_ISSTOCK=1,ST_PRICETIPS='',ST_CURR='HKD',ST_IMG='https://img.vipstation.com.hk/one.jpg')
    def test_classification_and_quote_validation(self):
        p=normalize(self.row)
        self.assertEqual((p['brand'],p['series'],p['model']),('Patek Philippe','Nautilus','5811/1G-001'))
        self.assertEqual(p['url'],'https://www.vipstation.com.hk/tc/item/one.html')
        self.assertIsNone(normalize(dict(self.row,NO_ISSTOCK=0)))
        self.assertIsNone(normalize(dict(self.row,NO_PRICE=0)))
        self.assertIsNone(normalize(dict(self.row,ST_PRICETIPS='請聯絡客服')))
        with self.assertRaises(ValueError):normalize(dict(self.row,ST_CURR='USD'))
    def test_variants_never_merge(self):
        p=normalize(self.row)
        self.assertNotEqual(p['variant_key'],normalize(dict(self.row,ST_NAME=self.row['ST_NAME'].replace('藍色','黑色')))['variant_key'])
        self.assertNotEqual(p['variant_key'],normalize(dict(self.row,ST_NAME=self.row['ST_NAME'].replace('99%','95%')))['variant_key'])
        self.assertEqual(variable('var itemList = [{"name":"semi;colon"}];','itemList')[0]['name'],'semi;colon')

if __name__=='__main__':unittest.main()
