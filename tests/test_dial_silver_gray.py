import unittest
from app import item_dial_color,dial_color_of,same_product_items,comparison_attributes

class DialSeparation(unittest.TestCase):
    def row(self,site,host,page,id,title,price):
        return dict(site=site,url=f'https://{host}/{page}?ID={id}',title='ROLEX DATEJUST 126334 '+title+' 2026年保卡 五株錶帶',price=price)
    def test_confirmed_silver_and_gray_not_same_group(self):
        own=self.row('鐘點站','www.hourstack.com.tw','product_open.asp','18351','銀灰色面盤',378000)
        other=self.row('永生','www.egps.com.tw','products_open.asp','199381','銀灰色面盤',518000)
        self.assertEqual(item_dial_color(own),'銀')
        self.assertEqual(item_dial_color(other),'灰')
        self.assertEqual(comparison_attributes(own)[0],'銀')
        self.assertEqual(same_product_items([own,other])['groups'],[])
    def test_true_silver_can_compare(self):
        own=self.row('鐘點站','www.hourstack.com.tw','product_open.asp','18351','銀灰色面盤',378000)
        other=self.row('永生','www.egps.com.tw','products_open.asp','other','銀色面盤',400000)
        groups=same_product_items([own,other])['groups']
        self.assertEqual(len(groups),1)
        self.assertEqual(groups[0]['dial_color'],'銀')
    def test_unconfirmed_ambiguous_dial_excluded(self):
        self.assertEqual(dial_color_of('126334 銀灰色面盤'),'')
        unknown=self.row('鐘點站','www.hourstack.com.tw','product_open.asp','new','銀灰色面盤',378000)
        self.assertEqual(item_dial_color(unknown),'')
    def test_correction_does_not_follow_reused_product_id(self):
        changed=self.row('鐘點站','www.hourstack.com.tw','product_open.asp','18351','藍色面盤',378000)
        self.assertEqual(item_dial_color(changed),'藍')
if __name__=='__main__':unittest.main()
