import unittest
import cv2
import numpy as np
import bezel_checks as bezel
import comparison_reviews as reviews
from unittest.mock import patch


class BezelChecks(unittest.TestCase):
    def row(self,title='',url='x'):
        return dict(site=url,url=url,title=title,image_url=url)

    def photo(self,seed=7,color=None):
        rng=np.random.default_rng(seed)
        im=np.full((480,480,3),235,np.uint8)
        yy,xx=np.ogrid[:480,:480];r=np.sqrt((xx-240)**2+(yy-240)**2)
        ring=(r>145)&(r<215)
        texture=rng.integers(20,220,(480,480),dtype=np.uint8)
        im[ring]=np.repeat(texture[:,:,None],3,axis=2)[ring]
        if color is not None:im[ring]=(im[ring].astype(float)*.2+np.array(color)*.8).astype(np.uint8)
        cv2.circle(im,(240,240),140,(25,25,25),-1)
        return im

    def features(self,im):return bezel.image_features(im,[.5,.5,175/480])

    def test_bezel_text_never_uses_dial_or_strap_colors(self):
        self.assertEqual(bezel.text_attributes('藍色面盤 黑色皮帶'),{})
        self.assertEqual(bezel.text_attributes('黑灰陶瓷圈')['color'],bezel.text_attributes('灰黑色錶圈')['color'])
        self.assertEqual(bezel.text_attributes('經典三角坑紋錶圈')['style'],'坑紋圈')
        self.assertNotEqual(bezel.text_attributes('單排鑽圈'),bezel.text_attributes('雙排鑽圈'))

    def test_text_alone_suffices_and_mismatch_does_not(self):
        self.assertTrue(bezel.match(self.row('黑灰陶瓷圈'),self.row('黑灰色錶圈'),{})['matched'])
        self.assertFalse(bezel.match(self.row('紅藍色錶圈'),self.row('黑灰陶瓷圈'),{})['matched'])
        self.assertFalse(bezel.match(self.row('坑紋錶圈'),self.row('光滑錶圈'),{})['matched'])

    def test_image_alone_suffices_after_geometric_matching(self):
        im=self.photo();rotated=cv2.warpAffine(im,cv2.getRotationMatrix2D((240,240),5,1), (480,480))
        a,b=self.features(im),self.features(rotated)
        self.assertTrue(bezel.images_match(a,b))
        result=bezel.match(self.row(url='a'),self.row(url='b'),{'a':{'bezel':a},'b':{'bezel':b}})
        self.assertTrue(result['matched']);self.assertEqual(result['method'],'圖片')
        self.assertFalse(bezel.images_match(a,self.features(self.photo(13))))
        self.assertFalse(bezel.images_match(a,self.features(self.photo(color=(20,160,30)))))

    def test_or_rule_accepts_either_source_even_if_other_does_not_match(self):
        im=self.features(self.photo())
        a,b=self.row('光滑錶圈','a'),self.row('坑紋錶圈','b')
        self.assertEqual(bezel.match(a,b,{'a':{'bezel':im},'b':{'bezel':im}})['method'],'圖片')
        b['title']='光滑錶圈'
        with patch.object(bezel,'images_match',return_value=False):self.assertEqual(bezel.match(a,b,{})['method'],'文字')

    def test_missing_evidence_stays_pending_in_shared_review_rule(self):
        b,o=self.row('黑色面盤','鐘點站'),self.row('黑色面盤','永生')
        self.assertEqual(reviews.pair_state(b,o,'黑','126334',{}, {})[1],'pending')
        b['title']+=' 黑灰陶瓷圈';o['title']+=' 黑灰色錶圈'
        self.assertEqual(reviews.pair_state(b,o,'黑','126334',{}, {})[1],'automatic')
        old=reviews.review_key(b,o,'黑','126334',{})
        o['title']='黑色面盤 紅藍色錶圈'
        self.assertNotEqual(old,reviews.review_key(b,o,'黑','126334',{}))


if __name__=='__main__':unittest.main()
