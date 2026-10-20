import copy
import unittest
from unittest.mock import patch
import push_notifications as push


def group(price=120,extra=False):
    rows=[{'site':'鐘點站','url':'clock','price':100},{'site':'永生','url':'other','price':price}]
    if extra:rows.append({'site':'玩錶舍','url':'new','price':110})
    return {'brand':'Rolex','model':'126334','dial_color':'灰','spread':price-100,'listings':rows}


class FakeDB:
    def __init__(self):self.state=None
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def execute(self,query,args=None):
        self.query=query
        if query.startswith('INSERT INTO push_comparison_state'):
            import json
            self.state=json.loads(args[1])
        return self
    def fetchone(self):
        if 'pg_try_advisory_lock' in self.query:return (True,)
        return (copy.deepcopy(self.state),) if self.state is not None else None
    def fetchall(self):return [('device',{})]


class ComparisonPushTests(unittest.TestCase):
    def test_price_or_added_listing_notify_but_order_and_removal_do_not(self):
        old,_=push.comparison_snapshot([group()])
        for value in (group(125),group(extra=True)):
            current,details=push.comparison_snapshot([value])
            self.assertEqual(len(push.comparison_updates(old,current,details)),1)
        value=group();value['listings'].reverse()
        current,details=push.comparison_snapshot([value])
        self.assertEqual(push.comparison_updates(old,current,details),[])
        self.assertEqual(push.comparison_updates(old,{},{}),[])
        self.assertEqual(push.comparison_snapshot([dict(group(),listings=[{'site':'永生','url':'other','price':120}])])[0],{})

    def test_first_run_silent_dedup_and_failed_push_retry(self):
        db=FakeDB();active=[group()]
        with patch.object(push,'configured',return_value=True),patch.object(push,'send') as send:
            run=lambda:push.notify_comparison_updates(lambda:db,lambda:{'groups':active})
            self.assertEqual(run()['initialized'],1);send.assert_not_called()
            active[0]=group(125)
            send.side_effect=RuntimeError('temporary provider error')
            self.assertEqual(run()['failed'],1)
            send.side_effect=None
            self.assertEqual(run()['sent'],1)
            self.assertEqual(run()['sent'],0)
            self.assertEqual(send.call_count,2)
            self.assertEqual(send.call_args.args[1]['url'],'/#comparisonSection')
