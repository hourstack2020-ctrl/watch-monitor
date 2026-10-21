"""Bezel text matching and conservative, local photo feature verification."""
import base64
import re
import cv2
import numpy as np

VERSION=1

def text_attributes(title):
    text=re.sub(r'\s+','',title or '').upper()
    result={}
    for pattern,value in [(r'雙排(?:鑽石|鑽)(?:錶)?圈','雙排鑽圈'),(r'單排(?:鑽石|鑽)(?:錶)?圈','單排鑽圈'),(r'(?:鑽石|鑲鑽|鑽)(?:錶)?圈','鑽圈'),(r'三角坑紋(?:錶)?圈|狗牙圈|坑紋(?:錶)?圈|FLUTEDBEZEL','坑紋圈'),(r'光滑(?:錶)?圈|光圈|SMOOTHBEZEL','光滑圈')]:
        if re.search(pattern,text):result['style']=value;break
    color=r'黑灰|灰黑|紅藍|藍紅|黑藍|藍黑|紅黑|黑紅|綠黑|黑綠|棕黑|黑棕|棕藍|藍棕|黑|白|灰|銀|金|藍|綠|紅|棕|粉紅|紫|黃|橘'
    for pattern,value in [(r'(?:陶瓷)(?:錶圈|圈)','陶瓷'),(r'(?:玫瑰金|永恒玫瑰金)(?:錶圈|圈)','玫瑰金'),(r'(?:白色黃金|白金)(?:錶圈|圈)','白金'),(r'(?:黃金)(?:錶圈|圈)','黃金'),(r'(?:鉑金)(?:錶圈|圈)','鉑金'),(r'(?:不鏽鋼|精鋼)(?:錶圈|圈)','精鋼')]:
        if re.search(pattern,text):result['material']=value;break
    match=re.search('(?<![白黃瑰鉑])('+color+r')(?:色|雙色|雙色陶瓷|色陶瓷|陶瓷)?(?:錶圈|陶瓷圈|外圈)',text)
    if match:result['color']=''.join(sorted(set(match[1])))
    return result

def text_label(item):
    attrs=text_attributes(item.get('title'))
    return '／'.join(attrs.values()) or '未辨識'

def image_features(im,circle):
    """Record ring-only ORB features, not full-image/background similarity."""
    h,w=im.shape[:2];side=min(h,w);x,y,r=circle
    x*=w;y*=h;r*=side
    yy,xx=np.ogrid[:h,:w];d=(xx-x)**2+(yy-y)**2
    # A broad ring accommodates inner/outer edge detections. Matching additionally
    # requires feature coverage in the outer ring, excluding dial-only matches.
    mask=np.uint8((d>(r*.80)**2)&(d<(r*1.30)**2))*255
    orb=cv2.ORB_create(nfeatures=360,edgeThreshold=10,fastThreshold=12)
    points,desc=orb.detectAndCompute(im,mask)
    if desc is None or len(points)<16:return {'status':'unverified','reason':'錶圈圖片細節不足'}
    order=sorted(range(len(points)),key=lambda i:-points[i].response)[:160]
    pts=[[(points[i].pt[0]-x)/r,(points[i].pt[1]-y)/r] for i in order]
    hsv=cv2.cvtColor(im,cv2.COLOR_BGR2HSV)[mask>0]
    colored=hsv[(hsv[:,1]>65)&(hsv[:,2]>40)&(hsv[:,2]<245)]
    hist=np.histogram(colored[:,0],bins=12,range=(0,180))[0].astype(float) if len(colored) else np.zeros(12)
    if hist.sum():hist/=hist.sum()
    return {'status':'analysed','version':VERSION,'points':np.round(pts,4).tolist(),
        'descriptors':base64.b64encode(desc[order].tobytes()).decode(),
        'color_fraction':round(len(colored)/len(hsv),3),'colors':np.round(hist,3).tolist()}

def images_match(left,right):
    if not all(x.get('status')=='analysed' and x.get('version')==VERSION for x in [left,right]):return False
    try:
        a=np.asarray(left['points'],np.float32);b=np.asarray(right['points'],np.float32)
        da=np.frombuffer(base64.b64decode(left['descriptors']),np.uint8).reshape(-1,32)
        db=np.frombuffer(base64.b64decode(right['descriptors']),np.uint8).reshape(-1,32)
        # A colored bezel must not match a neutral ring or a different palette.
        fa,fb=left['color_fraction'],right['color_fraction']
        if (fa>.20)!=(fb>.20):return False
        if max(fa,fb)>.20 and np.abs(np.asarray(left['colors'])-np.asarray(right['colors'])).sum()>.55:return False
        pairs=cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(da,db,k=2)
        good=[m for pair in pairs if len(pair)==2 for m,n in [pair] if m.distance<.70*n.distance and m.distance<48]
        if len(good)<12:return False
        aa=np.float32([a[m.queryIdx] for m in good]);bb=np.float32([b[m.trainIdx] for m in good])
        _,inliers=cv2.findHomography(aa,bb,cv2.RANSAC,.06)
        if inliers is None:return False
        valid=inliers.ravel().astype(bool);aa=aa[valid];bb=bb[valid]
        if len(aa)<10 or valid.mean()<.70:return False
        # Require many geometric inliers across both sides of the ring and outer-rim support.
        def spread(pts):
            return len(set((int(p[0]>=0),int(p[1]>=0)) for p in pts))>=2
        outer=max(sum(np.linalg.norm(p)>1.02 for p in pts) for pts in [aa,bb])
        return bool(len(aa)>=20 and spread(aa) and spread(bb) and outer>=4)
    except (KeyError,ValueError,TypeError,cv2.error):return False

def match(left,right,evidence):
    a=text_attributes(left.get('title'));b=text_attributes(right.get('title'))
    shared=set(a)&set(b)
    text_match=bool(shared) and all(a[k]==b[k] for k in shared)
    if text_match:return {'matched':True,'method':'文字','label':text_label(left)}
    photo_match=images_match((evidence.get(left.get('image_url')) or {}).get('bezel',{}),(evidence.get(right.get('image_url')) or {}).get('bezel',{})) if evidence is not None else False
    if photo_match:return {'matched':True,'method':'圖片','label':text_label(left)}
    return {'matched':False,'method':'待確認','label':text_label(left),'reason':'錶圈文字或圖片尚未確認相符'}

def listing_info(row,listings,evidence):
    partners=[x for x in listings if (x.get('site')=='鐘點站')!=(row.get('site')=='鐘點站')]
    checks=[match(row,x,evidence) for x in partners]
    methods=sorted({x['method'] for x in checks if x['matched']})
    method='／'.join(methods) if methods else '使用者確認'
    label=text_label(row)
    if label=='未辨識' and any('圖片' in x for x in methods):label='圖片已確認'
    return {'bezel':label,'bezel_method':method}
