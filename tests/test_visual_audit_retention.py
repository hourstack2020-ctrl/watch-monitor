import unittest,hashlib
from unittest.mock import patch
import dial_images
class VisualAuditRetention(unittest.TestCase):
    def test_same_photo_retains_verified_colour(self):
        previous={'visual_verified':True,'sha256':hashlib.sha256(b'photo').hexdigest(),'status':'analysed','family':'purple','tone':'light'}
        with patch.object(dial_images,'analyse_image',return_value={'status':'analysed','family':'blue','tone':'light'}):
            result=dial_images.analyse_with_visual_review(b'photo',previous)
        self.assertEqual(result['family'],'purple');self.assertEqual(result['automated_result']['family'],'blue')
    def test_replaced_photo_invalidates_visual_review(self):
        previous={'visual_verified':True,'sha256':hashlib.sha256(b'old').hexdigest(),'family':'purple'}
        with patch.object(dial_images,'analyse_image',return_value={'status':'analysed','family':'green','tone':'dark'}):
            result=dial_images.analyse_with_visual_review(b'new',previous)
        self.assertEqual(result['family'],'green');self.assertNotIn('visual_verified',result)
