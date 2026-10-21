import unittest
import app


class BlueSubmarinerComparisons(unittest.TestCase):
    def test_same_price_2023_listing_compares_without_approval(self):
        own=dict(site='鐘點站',url='https://www.hourstack.com.tw/product_open.asp?ID=18469',
            title='ROLEX 勞力士 Submariner 潛航者 126613LB 半金藍 藍水鬼 18K黃金 半金款 126613 LB 陶瓷圈 藍色面盤 2023年新式保卡',
            price=535000,year='2023',condition='9成5新 附原廠盒單',missing_runs=0)
        other=dict(site='雷達站',url='https://www.rdwatch.com.tw/product_open.asp?ID=29652',
            title='ROLEX 勞力士 Submariner 126613LB半金藍水鬼 最新款3235機芯 2023年新式保卡',
            price=535000,year='2023',condition='9成5新 原廠盒單',missing_runs=0)
        self.assertEqual(app.item_dial_color(other),'藍')
        result=app.same_product_items([own,other],{}, {})
        self.assertEqual(len(result['groups']),1)
        self.assertEqual(result['groups'][0]['dial_color'],'藍')
        self.assertEqual(result['groups'][0]['spread'],0)
        self.assertEqual(result['review_pairs'],[])
        self.assertEqual(result['items'][0]['difference'],0)

    def test_other_references_and_custom_dials_do_not_inherit_nickname(self):
        for ref in ['126610LN','126613LN','126710BLNR']:
            self.assertEqual(app.dial_color_of('ROLEX '+ref+' 藍水鬼'),'')
        for suffix in ['改裝','隕石面盤','副廠','彩色面盤']:
            self.assertEqual(app.dial_color_of('ROLEX 126613LB 藍水鬼 '+suffix),'')
        self.assertEqual(app.dial_color_of('ROLEX 126613LB 藍水鬼 黑色面盤'),'黑')


if __name__=='__main__':unittest.main()
