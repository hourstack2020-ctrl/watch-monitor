import unittest
from app import dial_color_of,same_product_items

class PandaDialChecks(unittest.TestCase):
    def test_white_panda_names_match_across_stores(self):
        titles=['ROLEX Daytona 126500LN 最新款白熊貓 2026年保卡','ROLEX Cosmograph Daytona 126500LN 計時碼表 白熊貓 白色面盤搭配黑色計時圈','ROLEX 迪通拿 126500LN 白迪 計時碼表 白熊貓 陶瓷錶圈']
        self.assertEqual(len({dial_color_of(t) for t in titles}),1)
        self.assertTrue(dial_color_of(titles[0]))
    def test_black_and_white_never_merge(self):
        rows=[dict(site=site,url=str(i),price=price,title='ROLEX Daytona 126500LN '+dial) for i,(site,price,dial) in enumerate([('鐘點站',1178000,'白熊貓'),('雷達站',1158000,'白熊貓'),('雷達站',973000,'黑熊貓')])]
        groups=same_product_items(rows)['groups']
        self.assertEqual(len(groups),1)
        self.assertEqual(groups[0]['listing_count'],2)
        self.assertEqual(groups[0]['spread'],20000)
    def test_ambiguous_or_conflicting_layouts_stay_excluded(self):
        for text in ['ROLEX Daytona 126500LN 熊貓','ROLEX Daytona 126500LN 白熊貓 黑色面盤','ROLEX Daytona 126500LN 白熊貓 黑色小面盤','ROLEX Daytona 126500LN 白熊貓 銀色計時圈','ROLEX Daytona 116508 白熊貓','ROLEX Daytona 126500LN 白熊貓 黑熊貓']:
            self.assertEqual(dial_color_of(text),'',text)
