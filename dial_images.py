"""Conservative local dial colour checks. No image can establish a watch reference."""
import hashlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urljoin
import cv2
import bezel_checks
import numpy as np
import requests
from PIL import Image

VERSION=1
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
    # Hough returns strongest circle first. Sample its inner area, avoiding bezel,
    # date window near the rim and the centre occupied by hands.
    x,y,r=candidates[0];yy,xx=np.ogrid[:h,:w];dist=(xx-x)**2+(yy-y)**2
    mask=(dist<(r*.68)**2)&(dist>(r*.16)**2)
    hsv=cv2.cvtColor(im,cv2.COLOR_BGR2HSV)[mask]
    if len(hsv)<800:return {'status':'review','reason':'面盤有效像素不足'}
    valid=(hsv[:,2]>20)&(hsv[:,2]<248)
    if valid.mean()<.55:return {'status':'review','reason':'面盤過暗或反光過強'}
    pixels=hsv[valid];coloured=pixels[:,1]>=35
    med=np.median(pixels,axis=0);fraction=float(coloured.mean())
    family='neutral';dominance=1-fraction
    if fraction>=.40:
        hue=pixels[coloured,0]
        bins=[('red',(hue<10)|(hue>=170)),('orange',(hue>=10)&(hue<23)),('yellow',(hue>=23)&(hue<38)),('green',(hue>=38)&(hue<85)),('cyan',(hue>=85)&(hue<100)),('blue',(hue>=100)&(hue<132)),('purple',(hue>=132)&(hue<170))]
        family,dominance=max(((name,float(m.mean())) for name,m in bins),key=lambda x:x[1])
        if dominance<.68:return {'status':'review','reason':'面盤混色或反光，待確認'}
    elif fraction>.18:return {'status':'review','reason':'色彩與無彩色比例接近，待確認'}
    else:dominance=1-fraction
    if family=='neutral':tone='light' if med[2]>=175 else 'dark' if med[2]<80 else 'mid'
    else:tone='light' if med[2]>=150 and med[1]<135 else 'dark' if med[2]<150 and med[1]>=135 else 'mid'
    return {'status':'analysed','reason':'','family':family,'tone':tone,'confidence':round(dominance,3),
        'bezel_version':bezel_checks.VERSION,'bezel':bezel_checks.image_features(im,[x/w,y/h,r/side]),
        'hsv':[round(float(v),2) for v in med],'circle':[round(x/w,4),round(y/h,4),round(r/side,4)],'sha256':hashlib.sha256(data).hexdigest()}

def analyse_with_visual_review(data,previous=None):
    result=analyse_image(data);digest=hashlib.sha256(data).hexdigest()
    # Reuse a visual audit only after re-downloading and checking the exact bytes.
    if previous and previous.get('visual_verified') and previous.get('sha256')==digest:
        result=dict(previous,automated_result=result,bezel=result.get('bezel',{}),bezel_version=bezel_checks.VERSION)
    result['sha256']=digest
    return result


def load_evidence(connection,rows):
    urls=list({r.get('image_url') for r in rows if r.get('image_url')})
    if not urls:return {}
    return {url:result for url,result in connection.execute("SELECT image_url,result FROM dial_image_analysis WHERE analyzer_version=%s AND image_url=ANY(%s) AND checked_at>=now()-interval '7 days'",(VERSION,urls)).fetchall()}

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
    if expected is None:return {'status':'review','reason':'特殊面盤需要人工確認'}
    if r.get('family') not in expected:return {'status':'conflict','reason':'商品文字與圖片色彩不一致'}
    if main in ('開心果綠','薄荷綠') and r.get('tone')=='dark':return {'status':'conflict','reason':'淺綠文字與深色面盤圖片不一致'}
    if main in ('深綠','墨綠') and r.get('tone')=='light':return {'status':'conflict','reason':'深綠文字與淺色面盤圖片不一致'}
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
                    ttl=timedelta(days=7) if old and old[2].get('status')=='analysed' else timedelta(hours=6)
                    if old and old[0]==VERSION and old[1]>now-ttl and old[2].get('bezel_version')==bezel_checks.VERSION:continue
                    if count>=limit:break
                    try:
                        data=download_image(session,url)
                        result=analyse_with_visual_review(data,old[2] if old and old[0]==VERSION else None)
                    except (requests.RequestException,ValueError,OSError,cv2.error,Image.DecompressionBombError) as exc:
                        result={'status':'review','reason':'圖片讀取或解析失敗，待確認'}
                        logging.warning('Dial image check failed for %s: %s',url,type(exc).__name__)
                    with connect() as c:
                        c.execute('''INSERT INTO dial_image_analysis(image_url,analyzer_version,checked_at,result) VALUES(%s,%s,now(),%s::jsonb)
                            ON CONFLICT(image_url) DO UPDATE SET analyzer_version=EXCLUDED.analyzer_version,checked_at=EXCLUDED.checked_at,result=EXCLUDED.result''',(url,VERSION,json.dumps(result)))
                    count+=1;time.sleep(1)
            return count
        finally:lock.execute('SELECT pg_advisory_unlock(68234018)')
