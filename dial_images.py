"""Conservative local dial colour checks. No image can establish a watch reference."""
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urljoin
import cv2
import bezel_checks
import official_references
import numpy as np
import requests
from PIL import Image

VERSION=1
FEATURE_VERSION=2
HOSTS={'www.hourstack.com.tw','hourstack.com.tw','www.egps.com.tw','egps.com.tw','www.playwatch.com.tw','playwatch.com.tw','www.rdwatch.com.tw','rdwatch.com.tw','www.watchstore.tw','watchstore.tw'}
cv2.setNumThreads(1)

def allowed_url(url):
    p=urlsplit(url)
    return p.scheme=='https' and p.hostname in HOSTS and p.port in (None,443) and not p.username and not p.password

def download_image(session,url):
    for _ in range(4):
        if not allowed_url(url):raise ValueError('圖片來源不在店家清單')
        with session.get(url,timeout=(8,18),stream=True,allow_redirects=False) as r:
            if r.status_code in (301,302,303,307,308):
                url=urljoin(url,r.headers.get('Location',''));continue
            r.raise_for_status()
            if not r.headers.get('Content-Type','').lower().startswith('image/'):raise ValueError('來源不是圖片')
            data=bytearray()
            for part in r.iter_content(65536):
                data.extend(part)
                if len(data)>4_000_000:raise ValueError('圖片過大，待確認')
            return bytes(data)
    raise ValueError('圖片重新導向過多')

def colour_profile(hsv):
    """Robust palette for one region; retain dark dial pixels, reject clipped glare."""
    if len(hsv)<40:return None
    valid=(hsv[:,2]>8)&(hsv[:,2]<248)
    if valid.mean()<.55:return None
    pixels=hsv[valid];coloured=pixels[:,1]>=35
    med=np.median(pixels,axis=0);fraction=float(coloured.mean())
    family='neutral';dominance=1-fraction
    if fraction>=.40:
        hue=pixels[coloured,0]
        bins=[('red',(hue<10)|(hue>=170)),('orange',(hue>=10)&(hue<23)),('yellow',(hue>=23)&(hue<38)),('green',(hue>=38)&(hue<85)),('cyan',(hue>=85)&(hue<100)),('blue',(hue>=100)&(hue<132)),('purple',(hue>=132)&(hue<170))]
        family,dominance=max(((name,float(m.mean())) for name,m in bins),key=lambda x:x[1])
        if dominance<.68:return None
    elif fraction>.18:return None
    if family=='neutral':tone='light' if med[2]>=175 else 'dark' if med[2]<80 else 'mid'
    else:tone='light' if med[2]>=150 and med[1]<135 else 'dark' if med[2]<150 and med[1]>=135 else 'mid'
    return dict(family=family,tone=tone,confidence=round(dominance,3),hsv=[round(float(v),2) for v in med])

def dial_features(im,circle):
    """Compare spatial regions so a hand, glare patch or subdial cannot dominate."""
    h,w=im.shape[:2];x,y,r=circle
    yy,xx=np.ogrid[:h,:w];distance=(xx-x)**2+(yy-y)**2
    angle=np.arctan2(yy-y,xx-x)
    mask=(distance<(r*.68)**2)&(distance>(r*.18)**2)
    if mask.sum()<800:return {'status':'review','reason':'面盤有效像素不足'}
    hsv=cv2.cvtColor(im,cv2.COLOR_BGR2HSV)
    sectors=[]
    for k in range(8):
        section=mask&(angle>=-np.pi+k*np.pi/4)&(angle<-np.pi+(k+1)*np.pi/4)
        profile=colour_profile(hsv[section])
        if profile:sectors.append(profile)
    if len(sectors)<5:return {'status':'review','reason':'面盤反光或遮擋過多'}
    families={p['family'] for p in sectors}
    family=max(sorted(families),key=lambda f:sum(p['family']==f for p in sectors))
    agreed=[p for p in sectors if p['family']==family]
    if len(agreed)<5 or len(agreed)/len(sectors)<.70:
        return {'status':'review','reason':'面盤分區色彩不一致','sectors':sectors}
    # A large brightness split is evidence of glare, gradient or multiple colours.
    tones=[p['tone'] for p in agreed]
    if 'light' in tones and 'dark' in tones and min(tones.count('light'),tones.count('dark'))>=2:
        return {'status':'review','reason':'面盤深淺差異過大','sectors':sectors}
    med=np.median([p['hsv'] for p in agreed],axis=0)
    tone=max(('light','mid','dark'),key=tones.count)
    # Keep separate chronograph regions for inspection; do not infer a reference
    # or force non-chronographs into a chronograph layout.
    regions={}
    for name,dx,dy in [('left',-.40,0),('right',.40,0),('bottom',0,.40)]:
        area=(xx-(x+r*dx))**2+(yy-(y+r*dy))**2<(r*.14)**2
        regions[name]=colour_profile(hsv[area])
    gray=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY)
    edges=cv2.Canny(gray,60,140)
    return dict(status='analysed',reason='',family=family,tone=tone,
        confidence=round(min(np.median([p['confidence'] for p in agreed]),len(agreed)/8),3),
        hsv=[round(float(v),2) for v in med],sectors=sectors,regions=regions,
        edge_density=round(float((edges[mask]>0).mean()),3))

def choose_circle(gray,candidates):
    """Score all candidates rather than trusting the first Hough detection."""
    h,w=gray.shape;side=min(h,w)
    edges=cv2.Canny(gray,60,140)
    def score(c):
        x,y,r=c
        angles=np.linspace(0,2*np.pi,96,endpoint=False)
        coverage=[]
        for a in angles:
            px=int(round(x+r*np.cos(a)));py=int(round(y+r*np.sin(a)))
            coverage.append(bool(edges[max(0,py-2):py+3,max(0,px-2):px+3].any()))
        centre=((x/w-.5)**2+(y/h-.45)**2)**.5
        return float(np.mean(coverage))+.45*r/side-.35*centre
    return max(candidates,key=score)

def analyse_image(data):
    # Decode dimensions before OpenCV to bound memory for external images.
    from io import BytesIO
    with Image.open(BytesIO(data)) as header:
        w,h=header.size
        if w*h>12_000_000 or min(w,h)<120:raise ValueError('圖片尺寸不適合辨識')
    im=cv2.imdecode(np.frombuffer(data,dtype=np.uint8),cv2.IMREAD_COLOR)
    if im is None:raise ValueError('圖片無法解碼')
    scale=min(1.,640/max(im.shape[:2]));im=cv2.resize(im,None,fx=scale,fy=scale)
    h,w=im.shape[:2];side=min(w,h)
    gray=cv2.GaussianBlur(cv2.cvtColor(im,cv2.COLOR_BGR2GRAY),(5,5),1)
    circles=cv2.HoughCircles(gray,cv2.HOUGH_GRADIENT,dp=1.2,minDist=side*.30,param1=100,param2=45,minRadius=int(side*.13),maxRadius=int(side*.44))
    if circles is None:return {'status':'review','reason':'無法可靠定位面盤'}
    candidates=[(float(x),float(y),float(r)) for x,y,r in circles[0] if .28*w<x<.72*w and .20*h<y<.73*h and x-r>0 and x+r<w and y-r>0 and y+r<h]
    if not candidates:return {'status':'review','reason':'面盤位置或拍攝角度待確認'}
    x,y,r=choose_circle(gray,candidates)
    result=dial_features(im,(x,y,r))
    result.update(feature_version=FEATURE_VERSION,bezel_version=bezel_checks.VERSION,
        bezel=bezel_checks.image_features(im,[x/w,y/h,r/side]),
        circle=[round(x/w,4),round(y/h,4),round(r/side,4)],sha256=hashlib.sha256(data).hexdigest())
    return result

def analyse_with_visual_review(data,previous=None):
    result=analyse_image(data);digest=hashlib.sha256(data).hexdigest()
    # Reuse a visual audit only after re-downloading and checking the exact bytes.
    if previous and previous.get('visual_verified') and previous.get('sha256')==digest:
        result=dict(previous,automated_result=result,feature_version=FEATURE_VERSION,
            bezel=result.get('bezel',{}),bezel_version=bezel_checks.VERSION)
    result['sha256']=digest
    result['feature_version']=FEATURE_VERSION
    result['bezel_version']=bezel_checks.VERSION
    result.pop('refresh_failed',None)
    return result


def load_evidence(connection,rows):
    urls=list({r.get('image_url') for r in rows if r.get('image_url')})
    images={url:result for url,result in connection.execute("SELECT image_url,result FROM dial_image_analysis WHERE analyzer_version=%s AND image_url=ANY(%s) AND checked_at>=now()-interval '7 days'",(VERSION,urls)).fetchall()} if urls else {}
    images['__official__']=official_references.load_checks(connection)
    return images

def assessment(row,dial,evidence):
    r=evidence.get(row.get('image_url')) or {}
    if r.get('status')!='analysed':return {'status':'review','reason':r.get('reason') or '圖片尚未核對'}
    main=dial.split('／')[0]
    expected=None
    if main in ('黑','白','銀','灰','煙燻灰'):expected={'neutral'}
    elif main=='綠松石':expected={'cyan','green'}
    elif '綠' in main:expected={'green'}
    elif '藍' in main:expected={'blue','cyan'}
    elif main=='紫':expected={'purple'}
    elif main in ('粉','粉紅','紅'):expected={'red','purple'}
    elif main in ('黃','金','香檳金','橘','巧克力','咖啡','棕','玫瑰金'):expected={'yellow','orange','red'}
    if expected is None:return {'status':'review','reason':'特殊面盤尚無可靠圖片色彩分類'}
    if r.get('family') not in expected:return {'status':'conflict','reason':'商品文字與圖片色彩不一致'}
    if main in ('開心果綠','薄荷綠') and r.get('tone')=='dark':return {'status':'conflict','reason':'淺綠文字與深色面盤圖片不一致'}
    if main in ('深綠','墨綠') and r.get('tone')=='light':return {'status':'conflict','reason':'深綠文字與淺色面盤圖片不一致'}
    sub=re.search(r'小錶盤(黑|白|銀)色',dial)
    if sub:
        # Audit labels protect the main palette; newly measured regions remain
        # independent evidence about the three chronograph subdials.
        measured=r.get('automated_result',r)
        regions=measured.get('regions') or {}
        opposite='light' if sub[1]=='黑' else 'dark'
        contradictory=sum(p is not None and p.get('family')=='neutral'
            and p.get('tone')==opposite and p.get('confidence',0)>=.85
            for p in regions.values())
        if contradictory>=2:return {'status':'conflict','reason':'小錶盤圖片與文字描述不一致'}
    # Brightness alone cannot reliably tell silver from grey. Text still has to
    # establish the exact colour; image tone only adds a conservative grouping.
    return {'status':'verified','reason':'圖文色彩已核對','bucket':r['family']+':'+r['tone']}

def refresh_images(connect,rows,limit=120):
    with connect() as lock:
        if not lock.execute('SELECT pg_try_advisory_lock(68234018)').fetchone()[0]:return 0
        try:
            existing={u:(v,t,r) for u,v,t,r in lock.execute('SELECT image_url,analyzer_version,checked_at,result FROM dial_image_analysis').fetchall()}
            urls=sorted({r.get('image_url') for r in rows if r.get('image_url')})
            now=datetime.now(timezone.utc);count=0
            with requests.Session() as session:
                session.headers['User-Agent']='HourStackDialCheck/1.0 (public product image colour verification)'
                for url in urls:
                    old=existing.get(url)
                    ttl=timedelta(days=7) if old and old[2].get('status')=='analysed' and not old[2].get('refresh_failed') else timedelta(hours=6)
                    if old and old[0]==VERSION and old[1]>now-ttl and old[2].get('bezel_version')==bezel_checks.VERSION and old[2].get('feature_version')==FEATURE_VERSION:continue
                    if count>=limit:break
                    try:
                        data=download_image(session,url)
                        result=analyse_with_visual_review(data,old[2] if old and old[0]==VERSION else None)
                    except (requests.RequestException,ValueError,OSError,cv2.error,Image.DecompressionBombError) as exc:
                        # A temporary download failure must not erase a prior audit.
                        result=dict(old[2]) if old and old[0]==VERSION else {'status':'review','reason':'圖片讀取或解析失敗，待確認'}
                        result.update(refresh_failed=True,feature_version=FEATURE_VERSION,bezel_version=bezel_checks.VERSION)
                        logging.warning('Dial image check failed for %s: %s',url,type(exc).__name__)
                    with connect() as c:
                        c.execute('''INSERT INTO dial_image_analysis(image_url,analyzer_version,checked_at,result) VALUES(%s,%s,now(),%s::jsonb)
                            ON CONFLICT(image_url) DO UPDATE SET analyzer_version=EXCLUDED.analyzer_version,checked_at=EXCLUDED.checked_at,result=EXCLUDED.result''',(url,VERSION,json.dumps(result)))
                    count+=1;time.sleep(1)
            return count
        finally:lock.execute('SELECT pg_advisory_unlock(68234018)')


