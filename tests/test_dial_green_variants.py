import unittest
from app import dial_color_of,item_dial_color,same_product_items

class GreenDials(unittest.TestCase):
    def row(self,site,host,id,dial,price):
        page='products_open.asp' if site=='永生' else 'product_open.asp'
        return dict(site=site,url=f'https://{host}/{page}?ID={id}',title='ROLEX Oyster Perpetual 36 蠔式恆動型 126000 '+dial+' OP36 2026年保卡',price=price)
    def test_pistachio_never_collapses_into_plain_green(self):
        self.assertEqual(dial_color_of('ROLEX 126000 開心果綠色面盤'),'開心果綠')
        self.assertEqual(dial_color_of('ROLEX 126000 牛油果綠色面盤'),'開心果綠')
        self.assertEqual(dial_color_of('ROLEX 126000 綠色面盤'),'綠')
        self.assertEqual(dial_color_of('ROLEX Oyster Perpetual 126000 開心果綠 最時尚'),'開心果綠')
    def test_correct_groups_include_matching_clock_pistachio(self):
        deep=self.row('鐘點站','www.hourstack.com.tw','18767','綠色面盤',268000)
        own=self.row('鐘點站','www.hourstack.com.tw','18011','開心果綠 最時尚',325000)
        other=self.row('永生','www.egps.com.tw','198697','開心果綠色面盤 牛油果綠',313000)
        self.assertEqual(item_dial_color(deep),'深綠')
        groups=same_product_items([deep,own,other])['groups']
        self.assertEqual(len(groups),1)
        self.assertEqual(groups[0]['dial_color'],'開心果綠')
        self.assertEqual({x['url'] for x in groups[0]['listings']},{own['url'],other['url']})
    def test_existing_green_variants_remain_separate(self):
        for text,expected in [('薄荷綠色面盤','薄荷綠'),('橄欖綠色面盤','橄欖綠'),('深綠色面盤','深綠')]:
            self.assertEqual(dial_color_of('ROLEX 126000 '+text),expected)
if __name__=='__main__':unittest.main()
