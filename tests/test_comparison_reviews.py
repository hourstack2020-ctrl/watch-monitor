import unittest
from unittest.mock import patch
from contextlib import contextmanager
import comparison_reviews as reviews
import app as monitor

class ComparisonReviews(unittest.TestCase):
    def setUp(self):
        self.b=dict(site='鐘點站',url='clock',image_url='clock.jpg',title='ROLEX 126000 綠色面盤 2026年保卡 五株錶帶 光滑錶圈',price=200)
        self.o=dict(site='永生',url='other',image_url='other.jpg',title='ROLEX 126000 綠色面盤 2026年保卡 五株錶帶 光滑錶圈',price=100)
        self.e={'clock.jpg':{'status':'review','reason':'面盤反光'},'other.jpg':{'status':'analysed','family':'green','tone':'light','sha256':'hash'}}
        self.key=reviews.review_key(self.b,self.o,'綠','126000',self.e)
    def test_uncertain_pair_displays_without_asking(self):
        d=monitor.same_product_items([self.b,self.o],self.e,{})
        self.assertEqual(len(d['groups']),1);self.assertEqual(d['review_pairs'],[])
        self.assertEqual(d['groups'][0]['unverified_count'],1)
        self.assertTrue(all(x['comparison_note'] for x in d['groups'][0]['listings']))
    def test_approve_keeps_exact_pair(self):
        d=monitor.same_product_items([self.b,self.o],self.e,{self.key:'approved'})
        self.assertEqual(len(d['groups']),1);self.assertEqual(d['groups'][0]['manual_review_count'],1)
        self.assertEqual(d['review_pairs'],[])
    def test_reject_suppresses_pair_even_after_image_verifies(self):
        e={x:{'status':'analysed','family':'green','tone':'light','sha256':x} for x in ['clock.jpg','other.jpg']}
        key=reviews.review_key(self.b,self.o,'綠','126000',e)
        self.assertEqual(monitor.same_product_items([self.b,self.o],e,{key:'rejected'})['groups'],[])
    def test_price_does_not_reask_but_new_picture_does(self):
        self.assertEqual(self.key,reviews.review_key(dict(self.b,price=300),self.o,'綠','126000',self.e))
        e=dict(self.e);e['other.jpg']=dict(e['other.jpg'],sha256='changed')
        self.assertNotEqual(self.key,reviews.review_key(self.b,self.o,'綠','126000',e))
    def test_changed_picture_matching_conditions_needs_no_confirmation(self):
        e={x:{'status':'analysed','family':'green','tone':'light','sha256':'new-'+x} for x in ['clock.jpg','other.jpg']}
        decisions={self.key:'rejected',reviews.listing_pair_id(self.b,self.o):self.key}
        self.assertEqual(reviews.pair_state(self.b,self.o,'綠','126000',e,decisions)[1],'automatic')
    def test_clear_matching_text_does_not_require_image_confirmation(self):
        for evidence in ({},self.e):
            self.assertEqual(reviews.pair_state(self.b,self.o,'開心果綠','126000',evidence,{})[1],'automatic')
    def test_conflicting_image_still_requires_confirmation(self):
        evidence={x:{'status':'analysed','family':'blue','tone':'light'} for x in ['clock.jpg','other.jpg']}
        self.assertEqual(reviews.pair_state(self.b,self.o,'開心果綠','126000',evidence,{})[1],'pending')
    def test_decision_endpoint_saves_only_current_pair(self):
        fields=('site','url','title','brand','model','year','condition','price','image_url')
        writes=[]
        outer=self
        class Result:
            def fetchall(self):return [tuple(row.get(f) for f in fields) for row in [outer.b,outer.o]]
        class DB:
            def execute(self,sql,args=None):
                if 'FROM watches' in sql:return Result()
                raise AssertionError(sql)
        @contextmanager
        def connect():yield DB()
        body=dict(decision='rejected',pair_key=self.key,baseline_url='clock',other_site='永生',other_url='other')
        with patch.object(monitor,'connect',connect),patch.object(monitor,'auth_ok',return_value=True),patch.object(monitor.dial_images,'load_evidence',return_value=self.e),patch.object(reviews,'save_decision',side_effect=lambda c,d,v:writes.append((d,v))):
            client=monitor.app.test_client()
            self.assertEqual(client.post('/api/comparison-review',json=body).status_code,403)
            r=client.post('/api/comparison-review',json=body,headers={'X-Watch-Monitor':'1'})
            self.assertEqual(r.status_code,200);self.assertEqual(writes[0][1],'rejected')
            body['pair_key']='stale'
            self.assertEqual(client.post('/api/comparison-review',json=body,headers={'X-Watch-Monitor':'1'}).status_code,409)
            self.assertEqual(len(writes),1)
    def test_manual_approval_does_not_override_year_for_alert(self):
        self.assertEqual(len(monitor.lower_price_items([self.b,self.o],self.e,{self.key:'approved'})['items']),1)
        different=dict(self.o,title=self.o['title'].replace('2026','2025'))
        self.assertEqual(monitor.lower_price_items([self.b,different],self.e,{self.key:'approved'})['items'],[])
    def test_pending_picture_does_not_notify_prematurely(self):
        self.assertEqual(reviews.pair_state(self.b,self.o,'綠','126000',{},{} )[1],'analysing')
    def test_review_push_sent_only_once_per_device(self):
        seen=set();details=reviews.review_details(self.key,self.b,self.o,'綠','126000','不確定')
        class Result:
            def __init__(self,row=None,rows=None):self.row=row;self.rows=rows or []
            def fetchone(self):return self.row
            def fetchall(self):return self.rows
        class DB:
            def execute(self,sql,args=None):
                if 'pg_try_advisory_lock' in sql:return Result((True,))
                if 'FROM push_subscriptions' in sql:return Result(rows=[('device',{})])
                if 'SELECT r.pair_key' in sql:return Result(rows=[] if 'device' in seen else [(details['pair_key'],details)])
                if 'INSERT INTO comparison_review_notifications' in sql:seen.add(args[0]);return Result()
                if 'pg_advisory_unlock' in sql:return Result()
                raise AssertionError(sql)
        @contextmanager
        def connect():yield DB()
        with patch.object(reviews.push,'configured',return_value=True),patch.object(reviews.push,'send') as send:
            self.assertEqual(reviews.notify_pending(connect)['sent'],1)
            self.assertEqual(reviews.notify_pending(connect)['sent'],0)
            self.assertEqual(send.call_count,1)
            self.assertEqual(send.call_args.args[1]['url'],'/#comparisonReview')

if __name__=='__main__':unittest.main()
