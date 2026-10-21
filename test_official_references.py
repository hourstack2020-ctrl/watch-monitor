import ast,json,re,unittest,urllib.parse
from pathlib import Path
from unittest.mock import patch
import official_references as official
import bezel_checks,dial_images,watchstore_source
import comparison_reviews

def application_rules():
    tree=ast.parse(Path('app.py').read_text())
    names={'brand_of','model_of','dial_color_of','item_dial_color','strap_of','item_strap',
        'visual_bucket','same_product_items','comparison_attributes','comparison_key',
        'reviewed_comparisons','image_comparison_candidates'}
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names or
        isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in {'BRANDS','MODEL','BASELINE_SITE','CONFIRMED_DIAL_COLORS'} for t in n.targets)]
    context=dict(re=re,urllib=urllib,dial_images=dial_images,bezel_checks=bezel_checks,
        comparison_reviews=comparison_reviews,official_references=official,watchstore_source=watchstore_source)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'app_rules','exec'),context)
    return context

class OfficialChecks(unittest.TestCase):
    def setUp(self):
        self.spec=next(x for x in official.CATALOG if x['model']=='126610LN')
        self.b=dict(site='鐘點站',url='https://a/item',brand='Rolex',model='126610LN',
            title='ROLEX Submariner 126610LN 黑色面盤 2026年保卡',price=400000,image_url='a',missing_runs=0)
        self.o=dict(self.b,site='永生',url='https://b/item',price=390000,image_url='b')
        self.verified={'__official__':{self.spec['key']:dict(status='verified',source_url=self.spec['url'],checked_at='2026-10-22T00:00:00Z')}}

    def test_unknown_bezel_waits_without_official_evidence(self):
        self.assertEqual(comparison_reviews.pair_state(self.b,self.o,'黑','126610LN',{}, {})[1],'pending')

    def test_verified_exact_official_reference_resolves_missing_bezel(self):
        self.assertEqual(comparison_reviews.pair_state(self.b,self.o,'黑','126610LN',self.verified,{})[1],'automatic')

    def test_image_conflict_cannot_be_erased_by_factory_specification(self):
        e=dict(self.verified,b=dict(status='analysed',family='green',tone='light'))
        self.assertEqual(comparison_reviews.pair_state(self.b,self.o,'黑','126610LN',e,{})[1],'pending')

    def test_different_dial_variant_cannot_use_same_reference(self):
        self.assertIsNone(official.pair_check(self.b,self.o,'126610LN','白',self.verified))

    def test_modified_listing_is_not_officially_verified(self):
        row=dict(self.o,title=self.o['title']+' 後鑲鑽圈')
        self.assertIsNone(official.pair_check(self.b,row,'126610LN','黑',self.verified))

    def test_explicit_conflicting_bezel_blocks_fallback(self):
        row=dict(self.o,title=self.o['title']+' 綠色陶瓷錶圈')
        self.assertIsNone(official.find_spec(row,'126610LN','黑'))

    def test_abbreviated_reference_does_not_inherit_full_reference(self):
        self.assertIsNone(official.find_spec(dict(self.b,title='PATEK PHILIPPE 4962/200R',brand='Patek Philippe'),'4962/200R-010','斑馬紋'))

    def test_search_links_in_navigation_cannot_verify_a_product(self):
        html=b'<title>Search</title><nav><h1>126610LN</h1>black dial black ceramic</nav><main>Not found</main>'
        self.assertEqual(official.verify_page(self.spec,html)['status'],'pending')

    def test_product_reference_and_all_characteristics_are_required(self):
        good=b'<h1>Submariner 126610LN</h1><main>black dial and black ceramic</main>'
        self.assertEqual(official.verify_page(self.spec,good)['status'],'verified')
        self.assertEqual(official.verify_page(self.spec,good.replace(b'black ceramic',b'green ceramic'))['status'],'pending')

    def test_pending_pair_not_in_groups_or_price_comparison(self):
        rules=application_rules();result=rules['same_product_items']([self.b,self.o],{}, {})
        self.assertEqual(result['groups'],[]);self.assertEqual(result['items'],[])
        self.assertEqual(result['image_pending_count'],1)

    def test_officially_verified_pair_visible_with_source_and_timestamp(self):
        rules=application_rules();result=rules['same_product_items']([self.b,self.o],self.verified,{})
        self.assertEqual(len(result['groups']),1)
        for row in result['groups'][0]['listings']:
            self.assertEqual(row['official_source_url'],self.spec['url'])
            self.assertTrue(row['official_checked_at'])
        self.assertEqual(result['groups'][0]['spread'],10000)

    def test_zebra_factory_reference_not_gem_gradient(self):
        rules=application_rules()
        text='PATEK PHILIPPE 4962/200R-010 原創斑馬紋飾錶盤 94顆漸層寶石錶圈'
        self.assertEqual(rules['dial_color_of'](text),'斑馬紋')
        self.assertNotEqual(rules['dial_color_of'](text.replace('-010','-001')),'斑馬紋')

if __name__=='__main__':unittest.main()
