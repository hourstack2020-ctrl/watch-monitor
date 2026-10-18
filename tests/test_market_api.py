import unittest
from contextlib import contextmanager
from datetime import date,datetime,timezone
from flask import Flask
import market_trends as m

class Result:
    def __init__(self,one=None,many=None):self.one=one;self.many=many or []
    def fetchone(self):return self.one
    def fetchall(self):return self.many
class DB:
    def execute(self,sql,args=None):
        day=date(2026,10,18);checked=datetime(2026,10,18,4,tzinfo=timezone.utc)
        if 'SELECT status,started' in sql:return Result(('completed',checked,checked,'','完成'))
        if 'SELECT EXISTS' in sql:return Result((False,))
        if 'FROM market_trend_runs' in sql:return Result((day,checked,1,{'menus':[]}))
        if 'FROM market_brand_snapshots' in sql:return Result(many=[])
        if 'FROM market_trend_products' in sql:
            if args[1]!=m.BRANDS['PP']:return Result(many=[])
            return Result(many=[('SKU','variant',m.BRANDS['PP'],'Nautilus','5811/1G','Example','','https://example.com',10000,None,[{'date':'2026-10-18','price':10000}],day)])
        raise AssertionError(sql)
class MarketAPI(unittest.TestCase):
    def test_existing_quotes_remain_readable_after_skipped_items_change(self):
        @contextmanager
        def connect():yield DB()
        app=Flask(__name__);app.testing=True
        m.install(app,connect,lambda f:f)
        response=app.test_client().get('/api/market-trends')
        self.assertEqual(response.status_code,200)
        data=response.get_json()
        self.assertEqual(data['items'][0]['model'],'5811/1G')
        self.assertEqual(data['items'][0]['price'],10000)
        self.assertEqual(data['items'][0]['date'],'2026-10-18')
        self.assertFalse(data['update_state']['running'])
        self.assertIn('menus',data['source_menu'])
if __name__=='__main__':unittest.main()
