import unittest
import cv2
import numpy as np
from dial_images import analyse_image,assessment,allowed_url
from app import same_product_items,lower_price_items

class DialImageChecks(unittest.TestCase):
    def image(self,dial):
        # A saturated green background and strap must not turn a blue dial green.
        im=np.full((480,640,3),(20,130,20),np.uint8)
        cv2.rectangle(im,(285,0),(355,480),(180,180,180),-1)
        cv2.circle(im,(320,240),175,(220,220,220),-1)
        cv2.circle(im,(320,240),150,dial,-1)
        cv2.line(im,(320,240),(390,190),(245,245,245),5)
        return cv2.imencode('.png',im)[1].tobytes()
    def test_detects_dial_instead_of_background(self):
        result=analyse_image(self.image((160,70,30)))
        self.assertEqual(result['status'],'analysed')
        self.assertEqual(result['family'],'blue')
    def test_text_image_conflict_excluded(self):
        row={'image_url':'image'}
        image={'status':'analysed','family':'blue','tone':'mid'}
        self.assertEqual(assessment(row,'綠',{'image':image})['status'],'conflict')
    def test_missing_image_never_auto_verifies(self):
        self.assertEqual(assessment({'image_url':''},'綠',{})['status'],'review')
    def test_visual_green_tones_do_not_merge(self):
        rows=[dict(site=site,url=site,title='ROLEX 126000 綠色面盤',price=1,image_url=site) for site in ['鐘點站','永生']]
        images={'鐘點站':{'status':'analysed','family':'green','tone':'dark'},'永生':{'status':'analysed','family':'green','tone':'light'}}
        self.assertEqual(same_product_items(rows,images)['groups'],[])
    def test_low_price_alert_requires_image_evidence(self):
        rows=[dict(site=site,url=site,title='ROLEX 126000 綠色面盤 2026年保卡 五株錶帶',price=price,image_url=site) for site,price in [('鐘點站',200),('永生',100)]]
        self.assertEqual(lower_price_items(rows,{})['items'],[])
        evidence={x['image_url']:{'status':'analysed','family':'green','tone':'dark'} for x in rows}
        self.assertEqual(len(lower_price_items(rows,evidence)['items']),1)
    def test_only_known_public_image_hosts(self):
        for url in ['http://www.egps.com.tw/x.jpg','https://127.0.0.1/x.jpg','https://www.egps.com.tw.evil.test/x.jpg','https://www.egps.com.tw:999/x.jpg']:
            self.assertFalse(allowed_url(url))
        self.assertTrue(allowed_url('https://www.egps.com.tw/product/a.jpg'))
    def test_blurred_solid_frame_not_a_verified_dial(self):
        data=cv2.imencode('.png',np.full((480,640,3),128,np.uint8))[1].tobytes()
        self.assertEqual(analyse_image(data)['status'],'review')
if __name__=='__main__':unittest.main()
