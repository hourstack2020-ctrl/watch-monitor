import unittest
from unittest.mock import patch
from contextlib import contextmanager
import market_trends as m

class Result:
    def __init__(self, row=None):self.row=row
    def fetchone(self):return self.row
class Connection:
    def __init__(self):self.statements=[]
    def execute(self,sql,args=None):
        self.statements.append((sql,args))
        return Result((True,) if 'pg_try_advisory_lock' in sql else None)

class BrandUpdates(unittest.TestCase):
    def setUp(self):
        self.db=Connection()
        @contextmanager
        def connect():yield self.db
        self.connect=connect
    def test_selected_brand_only(self):
        with patch.object(m,'fetch_catalog',return_value=([{'source_id':'1'}],2,3,{})) as fetch,patch.object(m,'save_brand_snapshot') as save:
            self.assertTrue(m.refresh_if_due(self.connect,force=True,brand_slug='patek-philippe'))
            self.assertEqual(fetch.call_count,1)
            self.assertEqual(fetch.call_args.args[1],'patek-philippe')
            self.assertEqual(save.call_args.args[1],'patek-philippe')
    def test_brand_failure_does_not_block_success(self):
        published=[]
        def fetch(progress,slug):
            if slug=='rolex':
                self.assertEqual(published,['patek-philippe'])
                raise ValueError('simulated source failure')
            return [{'source_id':slug}],1,1,{}
        def save(connect,slug,*args):published.append(slug)
        with patch.object(m,'fetch_catalog',side_effect=fetch),patch.object(m,'save_brand_snapshot',side_effect=save),patch.object(m.logging,'exception'):
            self.assertTrue(m.refresh_if_due(self.connect,force=True))
        self.assertEqual(published,['patek-philippe','richard-mille','audemars-piguet'])
        final=[args for sql,args in self.db.statements if "status=%s,finished" in sql][-1]
        self.assertEqual(final[0],'partial')
        self.assertIn('Rolex',final[1])
    def test_invalid_brand_never_connects(self):
        with self.assertRaises(ValueError):m.refresh_if_due(lambda:self.fail('must not connect'),brand_slug='invalid')
    def test_selected_series(self):
        self.assertIn('Aquanaut',m.VISIBLE_SERIES['Patek Philippe 百達翡麗'])
        self.assertNotIn('Gondolo',m.VISIBLE_SERIES['Patek Philippe 百達翡麗'])
        self.assertNotIn('Royal Oak Offshore 皇家橡樹離岸系列',m.VISIBLE_SERIES['Audemars Piguet 愛彼'])
if __name__=='__main__':unittest.main()
