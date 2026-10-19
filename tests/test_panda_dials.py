import unittest
from app import dial_color_of,item_dial_color,same_product_items

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

    def test_verified_clock_photo_supplies_missing_black_dial(self):
        own=dict(site='鐘點站',url='https://www.hourstack.com.tw/product_open.asp?ID=18357',title='ROLEX Cosmograph Daytona 126500LN 計時碼表 秒殺經典款 2026年保卡',image_url='https://www.hourstack.com.tw/product/product_big/66A02155-BD9F-4003-B890-0CA49DFD3444.JPG',price=948000)
        other=dict(site='永生',url='other',title='ROLEX Daytona 126500LN 黑熊貓 亮黑色面盤搭配銀色計時圈',price=963000)
        self.assertEqual(item_dial_color(own),dial_color_of(other['title']))
        self.assertEqual(len(same_product_items([own,other],{}, {})['groups']),1)
        self.assertEqual(item_dial_color(dict(own,image_url='https://www.hourstack.com.tw/new.jpg')),'')
        self.assertEqual(item_dial_color(dict(own,title=own['title']+' 白色面盤')),'')
        self.assertEqual(item_dial_color(dict(own,title=own['title'].replace('126500LN','116500LN'))),'')
