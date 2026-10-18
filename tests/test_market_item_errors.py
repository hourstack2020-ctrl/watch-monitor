import json
import unittest
from unittest.mock import patch
import requests
import market_trends as m

class Cookies:
    def set(self,*args,**kwargs):pass
class Response:
    def __init__(self,text='',status=200):self.text=text;self.status=status
    def raise_for_status(self):
        if self.status>=400:raise requests.HTTPError(str(self.status))
class Client:
    def __init__(self,detail_failure=False):self.cookies=Cookies();self.headers={};self.detail_failure=detail_failure
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def get(self,url,**kwargs):
        if '/watches/' in url:
            items=[dict(ST_CODE=code,ST_ITEMGROUP='RICHARD MILLE',ST_NAME='Richard Mille RM11-03 TI',NO_PRICE=12345,NO_ISSTOCK=1,ST_CURR='HKD',ST_IMG='',ST_WEB_NAME=code) for code in ['bad','good']]
            data={'deptList':{'ST_TITLE':m.BRAND_SLUGS['richard-mille']},'otherList':[],'pageInfo':{'currentpage':1,'totpage':1},'itemList':items}
            return Response(';'.join('var '+k+' = '+json.dumps(v) for k,v in data.items()))
        if '/bad.html' in url:return Response(status=404)
        if self.detail_failure:return Response('var iteminfo = {}')
        return Response('var iteminfo = '+json.dumps({'ST_CODE':'good','ST_WEB_SUBCATALOG':m.BRAND_SLUGS['richard-mille'],'ST_TYPE':'RM11-03 TI'}))

class ItemErrors(unittest.TestCase):
    def test_404_skips_item_and_continues(self):
        with patch.object(m.requests,'Session',return_value=Client()),patch.object(m.time,'sleep'),patch.object(m.logging,'warning'):
            products,pages,total,metadata=m.fetch_catalog(brand_slug='richard-mille')
        self.assertEqual([p['source_id'] for p in products],['good'])
        self.assertEqual(metadata['skipped_count'],1)
        self.assertEqual(metadata['skipped_items'][0]['source_id'],'bad')
        self.assertEqual(total,2)
    def test_no_valid_products_keeps_previous_snapshot(self):
        with patch.object(m.requests,'Session',return_value=Client(True)),patch.object(m.time,'sleep'),patch.object(m.logging,'warning'):
            with self.assertRaises(ValueError):m.fetch_catalog(brand_slug='richard-mille')
    def test_listing_page_error_still_fails_brand(self):
        client=Client()
        client.get=lambda *a,**kw:Response(status=503)
        with patch.object(m.requests,'Session',return_value=client),patch.object(m.time,'sleep'):
            with self.assertRaises(requests.HTTPError):m.fetch_catalog(brand_slug='richard-mille')
if __name__=='__main__':unittest.main()
