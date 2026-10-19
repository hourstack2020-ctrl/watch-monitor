import unittest
from app import dial_color_of
class DialAuditRules(unittest.TestCase):
    def test_bezel_and_strap_colours_do_not_remove_explicit_dial(self):
        self.assertEqual(dial_color_of('ROLEX GMT-Master II 126710GRNR 黑色面盤 灰黑雙色陶瓷錶圈'),'黑')
        self.assertEqual(dial_color_of('ROLEX Datejust 126334 白色面盤 雙色錶帶'),'白')
        self.assertEqual(dial_color_of('ROLEX 126334 雙色面盤'),'')
    def test_roman_short_name_and_full_description_match(self):
        self.assertEqual(dial_color_of('ROLEX Datejust 278273 白羅馬'),dial_color_of('ROLEX Datejust 278273 白色面盤 羅馬數字時標'))
    def test_honeycomb_and_spacing_preserve_exact_texture(self):
        self.assertEqual(dial_color_of('ROLEX Land-Dweller 127334 白色蜂巢面'),'白／蜂巢紋')
        self.assertEqual(dial_color_of('ROLEX Land-Dweller 127334 醇 白 色 蜂 巢 圖 案 錶 面'),'白／蜂巢紋')
        self.assertNotEqual(dial_color_of('ROLEX 127334 白色蜂巢面'),dial_color_of('ROLEX 127334 白色面盤'))
    def test_specific_named_variants_remain_distinct(self):
        self.assertEqual(dial_color_of('ROLEX Datejust 126334 溫布頓'),'灰／溫布頓／羅馬時標')
        self.assertEqual(dial_color_of('ROLEX Datejust 126334 溫布敦灰色綠羅馬面盤'),'灰／溫布頓／羅馬時標')
        self.assertEqual(dial_color_of('ROLEX Datejust 126334 薄荷綠'),'薄荷綠')
        self.assertEqual(dial_color_of('ROLEX Datejust 126334 薄荷綠色錶帶'),'')
        self.assertEqual(dial_color_of('ROLEX Oyster Perpetual 124200 開心果綠'),'開心果綠')
    def test_only_unambiguous_water_ghost_name_is_classified(self):
        self.assertEqual(dial_color_of('ROLEX Submariner 126610LN 黑水鬼'),'黑')
        self.assertEqual(dial_color_of('ROLEX Submariner 126610LV 綠水鬼'),'')
    def test_previous_generation_pandas_keep_separate_dials(self):
        self.assertEqual(dial_color_of('ROLEX Daytona 116500LN 白熊貓'),'白／小錶盤白色／計時圈黑色')
        self.assertNotEqual(dial_color_of('ROLEX Daytona 116500LN 白熊貓'),dial_color_of('ROLEX Daytona 116500LN 黑熊貓'))
