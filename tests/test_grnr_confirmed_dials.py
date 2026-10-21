import unittest
import app as monitor


class ConfirmedGrnrDials(unittest.TestCase):
    def setUp(self):
        self.baseline=dict(site='鐘點站',url='https://www.hourstack.com.tw/product_open.asp?ID=18252',
            title='ROLEX GMT-Master II 126710GRNR 五株 第二時區綠針 黑灰陶瓷圈 2026年木紋保卡',
            image_url='https://www.hourstack.com.tw/product/product_big/384EB9E8-4348-4CCA-9B89-687E2F1FD0C6.JPG',
            price=678000,year='2026',condition='9成9成珍藏品')
        self.other=dict(site='雷達站',url='https://www.rdwatch.com.tw/product_open.asp?ID=29076',
            title='ROLEX GMT-Master II 126710GRNR 最新款不鏽鋼材質 搭配黑灰色錶圈 紀念型（Jubilee）錶帶 2026年新式保卡',
            image_url='https://www.rdwatch.com.tw/product/product_big/19471-325.JPG',
            price=668000,year='2026',condition='9成9新珍藏品')

    def test_bezel_text_alone_remains_unknown(self):
        self.assertEqual(monitor.dial_color_of(self.baseline['title']),'')
        self.assertEqual(monitor.dial_color_of(self.other['title']),'')

    def test_verified_photos_restore_comparison_and_price_difference(self):
        for row in [self.baseline,self.other]:self.assertEqual(monitor.item_dial_color(row),'黑')
        result=monitor.same_product_items([self.baseline,self.other],{}, {})
        self.assertEqual(len(result['groups']),1)
        self.assertEqual(result['groups'][0]['dial_color'],'黑')
        self.assertEqual(result['items'][0]['difference'],10000)
        self.assertEqual(result['review_pairs'],[])
        self.assertEqual(monitor.lower_price_items([self.baseline,self.other],{}, {})['items'][0]['difference'],10000)

    def test_changed_photo_and_other_reference_do_not_inherit_confirmation(self):
        self.assertEqual(monitor.item_dial_color(dict(self.other,image_url='https://www.rdwatch.com.tw/new.jpg')),'')
        self.assertEqual(monitor.item_dial_color(dict(self.other,title=self.other['title'].replace('126710GRNR','126710BLNR'))),'')
        self.assertEqual(monitor.item_dial_color(dict(self.other,site='其他')),'')

    def test_explicit_other_dial_and_modified_dials_keep_existing_rules(self):
        self.assertEqual(monitor.item_dial_color(dict(self.other,title=self.other['title']+' 藍色面盤')),'藍')
        for word in ['改裝','隕石面盤','彩色面盤','滿天星','藍色面盤 白色面盤']:
            self.assertNotEqual(monitor.item_dial_color(dict(self.other,title=self.other['title']+' '+word)),'黑')


if __name__=='__main__':unittest.main()
