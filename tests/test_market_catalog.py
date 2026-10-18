import sys,json,unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from market_trends import fetch_catalog,BRANDS

class SourceTest(unittest.TestCase):
    def test_only_four_brands_and_source_menus(self):
        slugs=dict(zip(['patek-philippe','rolex','richard-mille','audemars-piguet'],BRANDS.items()))
        visited=[]
        class Client:
            headers={}
            cookies=type('Cookies',(),{'set':lambda *a,**k:None})()
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def get(self,url,params=None,**kwargs):
                visited.append(url)
                slug=url.rsplit('/',1)[-1]
                group,brand=slugs[slug]
                item=dict(ST_CODE='58111G001',ST_WEB_NAME='test',ST_ITEMGROUP=group,ST_NAME='Nautilus 5811/1G-001 18kt',NO_PRICE=800000,NO_ISSTOCK=1,ST_CURR='HKD',ST_PRICETIPS='')
                data=dict(deptList={'ST_TITLE':brand},otherList=[{'ST_CODE':'st_series','LT_VALUES':['原站正式系列']},{'ST_CODE':'no_price','LT_VALUES':['0 - 999999']}],pageInfo={'currentpage':1,'totpage':1},itemList=[dict(item,ST_CODE=str(list(slugs).index(slug))+'58111G001')])
                # Make the model a literal prefix of its source SKU.
                data['itemList'][0]['ST_NAME']=data['itemList'][0]['ST_CODE']+' 18kt'
                text=''.join('var '+k+'='+json.dumps(v,ensure_ascii=False)+';' for k,v in data.items())
                return type('Response',(),{'text':text,'raise_for_status':lambda self:None})()
        with patch('market_trends.requests.Session',Client),patch('market_trends.time.sleep'):
            products,pages,count,metadata=fetch_catalog()
        self.assertEqual(len(products),4)
        self.assertEqual(len(metadata['menus']),4)
        self.assertTrue(all(x['series']=='原站正式系列' for x in products))
        self.assertTrue(all('/tc/watches/' in u for u in visited))
        self.assertEqual(set(x['brand'] for x in products),set(BRANDS.values()))

if __name__=='__main__':unittest.main()
