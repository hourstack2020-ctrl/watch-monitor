import hashlib
import unittest
from unittest.mock import patch
import cv2
import numpy as np
import dial_images as d

class DialImageTests(unittest.TestCase):
    def dial(self,color):
        im=np.full((320,320,3),color,np.uint8)
        return im

    def test_dark_pixels_not_discarded_as_black_background(self):
        r=d.dial_features(self.dial((15,15,15)),(160,160,130))
        self.assertEqual((r['status'],r['family'],r['tone']),('analysed','neutral','dark'))

    def test_small_glare_and_hand_do_not_change_green(self):
        im=self.dial((40,140,40))
        cv2.line(im,(160,160),(230,100),(255,255,255),8)
        cv2.circle(im,(200,190),18,(255,255,255),-1)
        r=d.dial_features(im,(160,160,130))
        self.assertEqual((r['status'],r['family']),('analysed','green'))

    def test_split_palette_not_reported_as_single_colour(self):
        im=self.dial((35,150,35));im[:,160:]=(160,50,30)
        self.assertEqual(d.dial_features(im,(160,160,130))['status'],'review')

    def test_glare_dominated_image_is_not_verified(self):
        self.assertEqual(d.dial_features(self.dial((255,255,255)),(160,160,130))['status'],'review')

    def test_pistachio_and_deep_green_have_distinct_tones(self):
        light=d.dial_features(self.dial((150,200,150)),(160,160,130))
        dark=d.dial_features(self.dial((20,90,20)),(160,160,130))
        self.assertEqual((light['family'],light['tone']),('green','light'))
        self.assertEqual((dark['family'],dark['tone']),('green','dark'))

    def test_chronograph_regions_keep_contrasting_subdial_colours(self):
        im=self.dial((210,210,210))
        for x,y in [(108,160),(212,160),(160,212)]:cv2.circle(im,(x,y),20,(30,30,30),-1)
        r=d.dial_features(im,(160,160,130))
        self.assertEqual(r['status'],'analysed')
        self.assertTrue(all(p['tone']=='dark' for p in r['regions'].values()))

    def test_circle_scoring_ignores_unsubstantiated_first_candidate(self):
        gray=np.zeros((320,320),np.uint8);cv2.circle(gray,(160,150),105,200,3)
        chosen=d.choose_circle(gray,[(130.,130.,45.),(160.,150.,105.)])
        self.assertEqual(chosen,(160.,150.,105.))

    def test_exact_image_audit_survives_feature_upgrade(self):
        data=b'same image';old=dict(status='analysed',visual_verified=True,
            sha256=hashlib.sha256(data).hexdigest(),family='purple',tone='mid')
        with patch.object(d,'analyse_image',return_value=dict(status='analysed',family='blue',tone='mid')):
            r=d.analyse_with_visual_review(data,old)
            self.assertEqual(r['family'],'purple')
            self.assertEqual(r['automated_result']['family'],'blue')
            self.assertEqual(r['feature_version'],d.FEATURE_VERSION)

    def test_changed_image_cannot_reuse_visual_audit(self):
        old=dict(visual_verified=True,sha256=hashlib.sha256(b'old').hexdigest(),family='purple')
        with patch.object(d,'analyse_image',return_value=dict(status='analysed',family='green')):
            self.assertEqual(d.analyse_with_visual_review(b'new',old)['family'],'green')

    def test_text_colour_conflict_remains_conflict(self):
        r=d.assessment({'image_url':'x'},'深綠',{'x':dict(status='analysed',family='green',tone='light')})
        self.assertEqual(r['status'],'conflict')

    def test_contrasting_subdials_do_not_pass_text_verification(self):
        evidence={'x':dict(status='analysed',family='neutral',tone='light',regions={
            'left':dict(family='neutral',tone='dark',confidence=.95),
            'right':dict(family='neutral',tone='dark',confidence=.95)})}
        r=d.assessment({'image_url':'x'},'白／小錶盤白色',evidence)
        self.assertEqual(r['status'],'conflict')

    def test_one_glare_region_does_not_override_black_subdial_text(self):
        evidence={'x':dict(status='analysed',family='neutral',tone='dark',regions={
            'left':dict(family='neutral',tone='light',confidence=.95),
            'right':dict(family='neutral',tone='dark',confidence=.95)})}
        self.assertEqual(d.assessment({'image_url':'x'},'黑／小錶盤黑色',evidence)['status'],'verified')

if __name__=='__main__':unittest.main()
