import unittest
import app

class APReferenceTests(unittest.TestCase):
    def test_full_reference_after_abbreviation(self):
        title='AUDEMARS PIGUET 愛彼 CODE 11.59系列 15210CR 煙燻灰 18K白金 正裝錶 2023年保卡 大三針 15210CR.OO.A002CR.01 玫瑰金 4302型自動上鍊 41mm'
        self.assertEqual(app.model_of(title),'15210CR.OO.A002CR.01')
        self.assertEqual(app.dial_color_of(title),'煙燻灰／太陽紋')

    def test_other_store_without_dial_noun(self):
        title='Audemars Piguet AP 愛彼錶 CODE 11.59 系列 顛覆傳統 15210CR.OO.A002CR.01 18K白金 玫瑰金雙色材質 煙燻灰色亮漆太陽紋 2022年保卡 自動上鍊 41mm'
        self.assertEqual(app.dial_color_of(title),'煙燻灰／太陽紋')

    def test_never_infer_from_smoky_grey_strap_or_conflicting_dial(self):
        base='Audemars Piguet CODE 11.59 15210CR.OO.A002CR.01 '
        self.assertNotEqual(app.dial_color_of(base+'煙燻灰皮帶'),'煙燻灰／太陽紋')
        self.assertNotEqual(app.dial_color_of(base+'煙燻灰 黑色面盤'),'煙燻灰／太陽紋')
