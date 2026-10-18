import unittest
from contextlib import contextmanager
from unittest.mock import patch
from datetime import datetime,timezone
import app as monitor

class Result:
    def __init__(self,rows):self.rows=rows
    def fetchall(self):return self.rows
class ImageComparisonAPI(unittest.TestCase):
    def response(self,evidence):
        now=datetime(2026,10,18,tzinfo=timezone.utc)
        rows=[(site,site,'ROLEX Oyster Perpetual 126000 綠色面盤','Rolex','126000','2026','二手',price,'image-'+site,now,'unchanged',0) for site,price in [('鐘點站',200),('永生',100)]]
        class DB:
            def execute(self,sql,args=None):
                if 'FROM watches' in sql:return Result(rows)
                if 'FROM dial_image_analysis' in sql:return Result(list(evidence.items()))
                raise AssertionError(sql)
        @contextmanager
        def connect():yield DB()
        with patch.object(monitor,'connect',connect),patch.object(monitor,'auth_ok',return_value=True):
            return monitor.app.test_client().get('/api/comparisons')
    def test_verified_comparison_api_returns_json(self):
        evidence={'image-'+site:{'status':'analysed','family':'green','tone':'dark'} for site in ['鐘點站','永生']}
        r=self.response(evidence);self.assertEqual(r.status_code,200)
        d=r.get_json();self.assertTrue(d['image_checked']);self.assertEqual(len(d['groups']),1)
    def test_unchecked_images_listed_for_review(self):
        r=self.response({});self.assertEqual(r.status_code,200)
        d=r.get_json();self.assertEqual(d['groups'],[]);self.assertEqual(len(d['image_review']),2)
if __name__=='__main__':unittest.main()
