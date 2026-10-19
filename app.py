import os, re, json, time, hmac, hashlib, logging, urllib.parse, subprocess, sys
from datetime import datetime, timezone, date, timedelta
from zoneinfo import ZoneInfo
from functools import wraps
from flask import Flask, request, jsonify, Response, send_file, session
import comparison_reviews
import dial_images
import requests, psycopg
import base64
from pwa_assets import ICONS, SERVICE_WORKER
import push_notifications as push
from bs4 import BeautifulSoup

app=Flask(__name__)
app.config.update(SECRET_KEY=os.getenv('SESSION_SECRET'),SESSION_COOKIE_NAME='hs_session',SESSION_COOKIE_SECURE=True,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',PERMANENT_SESSION_LIFETIME=timedelta(days=30))
logging.basicConfig(level=logging.INFO)
BASELINE_SITE='鐘點站'
SITES={'鐘點站':'https://www.hourstack.com.tw/product.asp','永生':'https://www.egps.com.tw/','玩錶舍':'https://www.playwatch.com.tw/','雷達站':'https://www.rdwatch.com.tw/'}
BRANDS={'ROLEX':'Rolex','PATEK PHILIPPE':'Patek Philippe','AUDEMARS PIGUET':'Audemars Piguet','OMEGA':'Omega','CARTIER':'Cartier','IWC':'IWC','HUBLOT':'Hublot','GRAND SEIKO':'Grand Seiko','CHOPARD':'Chopard','ZENITH':'Zenith','RICHARD MILLE':'Richard Mille','VACHERON CONSTANTIN':'Vacheron Constantin','JAEGER':'Jaeger-LeCoultre','FRANCK MULLER':'Franck Muller','TUDOR':'Tudor','PANERAI':'Panerai','BVLGARI':'Bvlgari','朗格':'A. Lange & Söhne'}
MODEL=re.compile(r'(?<![A-Za-z0-9])(?:[A-Z]{0,5}\d{3,8}[A-Z]{0,5}(?:[./-][A-Z0-9]{1,12}){0,4}|\d{2,6}[./-][A-Z0-9]{2,10}(?:[./-][A-Z0-9]{2,12}){0,3})(?![A-Za-z0-9])',re.I)
BRANDS.update({'GRANDSEIKO':'Grand Seiko','BLANCPAIN':'Blancpain','BREGUET':'Breguet','BREITLING':'Breitling','BOVET':'Bovet','BELL & ROSS':'Bell & Ross','CHANEL':'Chanel','DIOR':'Dior','DANIEL ROTH':'Daniel Roth','GIRARD':'Girard-Perregaux','GLASHUTTE':'Glashütte Original','格拉蘇蒂':'Glashütte Original','MOSER':'H. Moser & Cie.','HAUTLENCE':'Hautlence','JAQUET DROZ':'Jaquet Droz','JACOB':'Jacob & Co.','LONGINES':'Longines','MONTBLANC':'Montblanc','MAURICE LACROIX':'Maurice Lacroix','MIDO':'Mido','ORIS':'Oris','PARMIGIANI':'Parmigiani Fleurier','PIAGET':'Piaget','ROGER DUBUIS':'Roger Dubuis','SEIKO':'Seiko','TAG HEUER':'TAG Heuer','ULYSSE NARDIN':'Ulysse Nardin'})

def connect():
    return psycopg.connect(os.environ['DATABASE_URL'],autocommit=False,connect_timeout=15,prepare_threshold=None)

def init_db():
    if os.environ.get('SKIP_DB_INIT') == '1':return
    with connect() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS watches(site TEXT NOT NULL,url TEXT NOT NULL,title TEXT,brand TEXT,model TEXT,year TEXT,condition TEXT,price BIGINT,price_text TEXT,updated TIMESTAMPTZ,last_seen TIMESTAMPTZ,status TEXT DEFAULT 'new',first_seen TIMESTAMPTZ DEFAULT now(),missing_runs INTEGER DEFAULT 0,PRIMARY KEY(site,url))''')
        c.execute('''CREATE TABLE IF NOT EXISTS history(id BIGSERIAL PRIMARY KEY,site TEXT,url TEXT,price BIGINT,checked TIMESTAMPTZ DEFAULT now())''')
        c.execute('''CREATE TABLE IF NOT EXISTS crawl_runs(id BIGSERIAL PRIMARY KEY,started TIMESTAMPTZ DEFAULT now(),finished TIMESTAMPTZ,status TEXT DEFAULT 'running',count INTEGER DEFAULT 0,errors TEXT DEFAULT '')''')
        c.execute('CREATE INDEX IF NOT EXISTS ix_watch_model ON watches(model)')
        c.execute('CREATE INDEX IF NOT EXISTS ix_history_url ON history(site,url,checked DESC)')
        c.execute('ALTER TABLE watches ADD COLUMN IF NOT EXISTS image_url TEXT')
        c.execute('ALTER TABLE watches ADD COLUMN IF NOT EXISTS source_order INTEGER')
        c.execute('ALTER TABLE watches ADD COLUMN IF NOT EXISTS price_changed_at TIMESTAMPTZ')
        c.execute('ALTER TABLE watches ADD COLUMN IF NOT EXISTS activity_at TIMESTAMPTZ')
        c.execute('''CREATE TABLE IF NOT EXISTS removal_events(id BIGSERIAL PRIMARY KEY,site TEXT NOT NULL,url TEXT NOT NULL,title TEXT,brand TEXT,model TEXT,year TEXT,condition TEXT,price BIGINT,image_url TEXT,last_seen TIMESTAMPTZ,detected_at TIMESTAMPTZ NOT NULL DEFAULT now())''')
        c.execute('CREATE INDEX IF NOT EXISTS ix_removal_events_detected ON removal_events(detected_at DESC,site)')
        c.execute("""CREATE TABLE IF NOT EXISTS listing_events(id BIGSERIAL PRIMARY KEY,site TEXT NOT NULL,url TEXT NOT NULL,event_type TEXT NOT NULL,title TEXT,brand TEXT,model TEXT,year TEXT,condition TEXT,price BIGINT,image_url TEXT,detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),snapshot_source TEXT NOT NULL DEFAULT 'observed')""")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_listing_first_seen ON listing_events(site,url) WHERE event_type IN ('initial','listed')")

def session_auth_version():
    return hmac.new((app.secret_key or '').encode(),os.environ.get('ADMIN_PASSWORD','').encode(),hashlib.sha256).hexdigest()

from account_settings import install as install_account_settings
auth_ok, account_login = install_account_settings(app, connect, session_auth_version)

def protected(fn):
    @wraps(fn)
    def inner(*a,**kw):
        if not auth_ok():return jsonify({'error':'登入已過期，請重新開啟 App 登入'}),401
        return fn(*a,**kw)
    return inner

def brand_of(t):
    u=t.upper()
    matches=[(u.index(k),-len(k),v) for k,v in BRANDS.items() if k in u]
    return min(matches)[2] if matches else '其他'

def model_of(t):
    u=t.upper()
    brand=brand_of(t)
    patterns={
        'Rolex':r'(?<![A-Z0-9])\d{5,6}[A-Z]{0,6}(?![A-Z0-9])',
        'Omega':r'(?<![A-Z0-9])(?:\d{3}\.\d{2}\.\d{2}\.\d{2}\.\d{2}\.\d{3}|\d{14})(?![A-Z0-9])',
        'IWC':r'(?<![A-Z0-9])IW\d{6}(?![A-Z0-9])',
        'Cartier':r'(?<![A-Z0-9])W[A-Z0-9]{7}(?![A-Z0-9])',
        'Panerai':r'(?<![A-Z0-9])PAM\s*\d{3,6}(?![A-Z0-9])',
        'Patek Philippe':r'(?<![A-Z0-9])\d{4}(?:/[A-Z0-9]+|[A-Z])(?:-\d{3})?(?![A-Z0-9])',
        'Audemars Piguet':r'(?<![A-Z0-9])\d{5}[A-Z]{2}(?:\.[A-Z0-9]+){0,4}(?![A-Z0-9])',
        'Jaeger-LeCoultre':r'(?<![A-Z0-9])Q\d[A-Z0-9]{5,9}(?![A-Z0-9])',
        'Longines':r'(?<![A-Z0-9])L(?:\d(?:\.\d{1,4}){3,5}|\d{7,13})(?![A-Z0-9])',
        'Breitling':r'(?<![A-Z0-9])[A-Z]{1,3}\d[A-Z0-9]{8,16}(?![A-Z0-9])',
        'Grand Seiko':r'(?<![A-Z0-9])[A-Z]{4}\d{3}(?![A-Z0-9])',
        'Glashütte Original':r'(?<![A-Z0-9])(?:[12](?:[-.]\d{2}){5}|[12]\d{10})(?![A-Z0-9])',
        'Hublot':r'(?<![A-Z0-9])\d{3}\.[A-Z0-9]{2}\.\d{4}\.[A-Z0-9]{2}(?:\.[A-Z0-9]+){0,3}(?![A-Z0-9])',
    }
    if brand in patterns:
        match=re.search(patterns[brand],u)
        return re.sub(r'\s+','',match.group()) if match else ''
    for m in MODEL.finditer(t):
        s=m.group().upper()
        if m.start()>0 and t[m.start()-1] in './-':continue
        if m.end()<len(t) and t[m.end()] in './-':continue
        if not re.fullmatch(r'20\d{2}|\d{2,3}MM|\d{1,3}',s):return s
    return ''

def dial_color_of(title):
    # Only explicit dial descriptions; never infer from bezel, strap or nickname.
    if re.search(r'(?:銀灰|灰銀)(?:色)?(?:太陽放射紋|太陽紋|放射紋)?(?:面盤|錶盤|錶面|面)',title):return ''
    # Reference-specific panda names describe distinct dial layouts, not just
    # a shared base colour. Keep the filled subdial and its contrasting ring separate.
    if model_of(title)=='126500LN' and re.search(r'DAYTONA|迪通拿',title,re.I):
        names=set(re.findall(r'(白|黑)熊貓',title))
        if len(names)==1 and not re.search(r'漸層|雙色|多色|彩色|滿天星|隕石|珍珠母貝|貝殼',title):
            main=next(iter(names));ring='黑' if main=='白' else '銀'
            explicit=set(re.findall(r'(黑|白|銀|金|灰|藍|綠)(?:色)?(?:面盤|錶盤|錶面)',title))
            sub=set(re.findall(r'(黑|白|銀|金|灰|藍|綠)(?:色)?(?:小錶盤|小面盤|子盤|計時盤|三眼)',title))
            rings=set(re.findall(r'(黑|白|銀|金|灰|藍|綠)(?:色)?計時圈',title))
            if explicit-{main} or sub-{main} or rings-{ring}:return ''
            return main+'／小錶盤'+main+'色／計時圈'+ring+'色'
    colors=r'開心果綠|牛油果綠|煙燻綠|煙燻藍|煙燻灰|天藍|蒂芙尼藍|TIFFANY藍|冰藍|淺藍|深藍|亮藍|海軍藍|午夜藍|薄荷綠|橄欖綠|墨綠|深綠|淺綠|綠松石|香檳金|香檳|玫瑰金|巧克力|咖啡|棕|褐|黑|白|銀|金|灰|藍|綠|紅|粉紅|粉|紫|黃|橘|橙'
    pattern=r'('+colors+r')(?:色)?(?:太陽放射紋|太陽紋|放射紋|波紋|條紋|巴黎釘紋|旭日紋|格紋|鏤空|漆|珍珠母貝|貝殼)?(?:面盤|錶盤|錶面|面)(?!盤?時標|框|圈)'
    found={m.group(1) for m in re.finditer(pattern,title)}
    # OP 36 listings also explicitly name the pistachio dial without a dial suffix.
    if not found and model_of(title)=='126000' and re.search(r'OYSTER\s*PERPETUAL|蠔式[恆恒]動',title,re.I):
        found.update(re.findall(r'(開心果綠|牛油果綠)(?:色)?',title))
    found={'開心果綠' if x=='牛油果綠' else x for x in found}
    # Distinct special dials must not collapse into a plain base color.
    if re.search(r'熊貓|漸層|漸藍|雙色|多色|彩色|滿天星|袖扣|項鍊|錶盒',title):return ''
    if re.search(r'漸變(?!煙燻)',title):return ''
    if len(found)!=1:return ''
    color=found.pop()
    color={'粉':'粉紅','香檳':'香檳金','褐':'棕','橙':'橘'}.get(color,color)
    variants=[]
    # Main colour alone cannot identify chronograph dial configurations.
    # Require explicit subdial colour; never infer it from the reference/nickname.
    chronograph=bool(re.search(r'DAYTONA|迪通拿|計時(?:碼[錶表]|腕[錶表]|功能)|CHRONOGRAPH',title,re.I))
    subcolors=set(re.findall(r'(黑|白|銀|金|香檳金|香檳|藍|灰|綠|棕)(?:色)?(?:小錶盤|小表盤|小面盤|子錶盤|子盤|計時盤|計時小盤|三眼)',title))
    subcolors.update(re.findall(r'(?:小錶盤|小表盤|子盤|計時盤)[：:\s]*(黑|白|銀|金|香檳金|香檳|藍|灰|綠|棕)(?:色)?',title))
    if chronograph and len(subcolors)!=1:return ''
    if subcolors:
        if len(subcolors)!=1:return ''
        variants.append('小錶盤'+subcolors.pop()+'色')
    for pattern,label in [
        (r'(?:鑽石|鑲鑽)(?:面盤|錶盤|面)|(?:面盤|錶盤)(?:鑲鑽|鑽石)','鑽面'),
        (r'(?:珍珠母貝|貝殼)(?:面盤|錶盤|面)','珍珠母貝'),
        (r'(?:隕石|隕石紋)(?:面盤|錶盤|面)','隕石'),
        (r'蜂巢(?:圖案|紋)?(?:面盤|錶盤|錶面|面)','蜂巢紋'),
        (r'(?:橫向雕紋|橫紋|條紋)(?:面盤|錶盤|錶面|面)','條紋'),
        (r'(?:太陽放射紋|太陽紋|放射紋|旭日紋)(?:面盤|錶盤|錶面|面)','太陽紋'),
        (r'波紋(?:面盤|錶盤|錶面|面)','波紋'),
        (r'羅馬(?:數字)?(?:時標|面盤|錶盤|面)','羅馬時標'),
        (r'(?:鑽石|鑲鑽)(?:時標|刻度)','鑽石時標'),
        (r'阿拉伯(?:數字)?(?:時標|面盤|錶盤|面)','阿拉伯時標'),
    ]:
        if re.search(pattern,title):variants.append(label)
    return '／'.join([color]+variants)


def condition_grade(value):
    value=re.sub(r'\s+','',value or '')
    if re.fullmatch(r'(?:全新)?未使用(?:品)?',value):return '未使用'
    m=re.match(r'(\d)成(\d{1,2})(?:新|成)',value)
    if m:return m[1]+'.'+m[2]+'成新'
    m=re.match(r'(\d\.\d{1,2})成新',value)
    return m[1]+'成新' if m else ''

def strap_of(title):
    title=re.sub(r'\s+','',title).upper()
    styles=[]
    for pattern,label in [
        (r'五[株銖珠]|JUBILEE|紀念型(?:錶帶|鏈帶|鍊帶|帶)', '五株鍊帶'),
        (r'三[板版節](?:式|型)?(?:錶帶|鏈帶|鍊帶|帶)|蠔式(?:[（(]OYSTER[）)])?(?:錶帶|鏈帶|鍊帶|三節錶帶)|OYSTERBRACELET', '三板蠔式鍊帶'),
        (r'總統型(?:錶帶|鏈帶|鍊帶)|PRESIDENTBRACELET', '總統型鍊帶'),
        (r'米蘭(?:編織)?(?:錶帶|鏈帶|鍊帶)|MILANESE', '米蘭鍊帶'),
    ]:
        if re.search(pattern,title):styles.append(label)
    # Leather/rubber/textile need explicit material and color, rather than
    # grouping every strap of that material together. Mixed/additional straps
    # remain unverified and are excluded.
    soft=re.findall(r'(黑|白|深藍|淺藍|天藍|藍|深棕|棕|咖啡|褐|綠|灰|紅)(?:色)?(鱷魚皮|鱷魚皮革|小牛皮|牛皮|橡膠|膠|尼龍|織物|織紋|帆布)(?:革)?(?:錶帶|帶)',title)
    for color,material in soft:
        material={'鱷魚皮革':'鱷魚皮','褐':'棕','膠':'橡膠'}.get(material,material)
        color={'褐':'棕'}.get(color,color)
        styles.append(color+'色'+material+'錶帶')
    if re.search(r'皮(?:革)?錶帶|膠(?:錶)?帶|尼龍|帆布|織紋錶帶',title) and not soft:return ''
    if re.search(r'副廠|改裝|另附|另贈|替換錶帶|更換錶帶',title):return ''
    return styles[0] if len(set(styles))==1 else ''

# User-confirmed dial colours apply only to these exact listings, not every 126334.
CONFIRMED_DIAL_COLORS = {
    ('鐘點站','www.hourstack.com.tw','18351'): '銀',
    ('永生','www.egps.com.tw','199381'): '灰',
}

def item_dial_color(item):
    title=item.get('title') or ''
    parsed=urllib.parse.urlsplit(item.get('url') or '')
    listing_id=urllib.parse.parse_qs(parsed.query).get('ID',[''])[0]
    # Exact listing colour verified from the user's photo; leave source text untouched.
    if (item.get('site'),parsed.hostname,listing_id)==('鐘點站','www.hourstack.com.tw','18767') and parsed.path.lower()=='/product_open.asp' and model_of(title)=='126000' and '126000 綠色面盤' in title:
        return dial_color_of(title.replace('126000 綠色面盤','126000 深綠色面盤',1))
    confirmed=CONFIRMED_DIAL_COLORS.get((item.get('site'),parsed.hostname,listing_id))
    if confirmed and parsed.path.lower()=='/product_open.asp' and model_of(title)=='126334' and '銀灰色面盤' in title:
        return dial_color_of(title.replace('銀灰色面盤',confirmed+'色面盤',1))
    # eGPS uses products_open.asp.
    if confirmed and parsed.path.lower()=='/products_open.asp' and model_of(title)=='126334' and '銀灰色面盤' in title:
        return dial_color_of(title.replace('銀灰色面盤',confirmed+'色面盤',1))
    return dial_color_of(title)


def comparison_attributes(item):
    title=item.get('title') or ''
    years=set(re.findall(r'(20\d{2})\s*年\s*(?:(?:新式|木紋|電子)\s*)*(?:保卡|保單|保證書)',title))
    return item_dial_color(item),(next(iter(years)) if len(years)==1 else ''),strap_of(title)

def comparison_key(item):
    brand=brand_of(item['title'])
    reference=model_of(item['title'])
    if not reference or brand=='其他':return None
    normalized=re.sub(r'[^A-Z0-9]','',reference.upper())
    if brand=='Panerai':normalized='PAM'+str(int(normalized[3:]))
    attributes=comparison_attributes(item)
    if not all(attributes):return None
    return (brand,normalized)+attributes

def visual_bucket(row,evidence):
    if evidence is None:return ()
    result=dial_images.assessment(row,item_dial_color(row),evidence)
    return (result['bucket'],) if result['status']=='verified' else None

def lower_price_with_images(rows):
    with connect() as c:
        evidence=dial_images.load_evidence(c,rows)
        decisions=comparison_reviews.load_decisions(c)
    return lower_price_items(rows,evidence,decisions)

def lower_price_items(rows,image_evidence=None,review_decisions=None):
    if image_evidence is not None:return reviewed_low_prices(rows,image_evidence,review_decisions or {})
    baseline={};active=[]
    for row in rows:
        if row.get('missing_runs',0)>0 or row.get('status')=='possibly_removed' or not row.get('price') or row['price']<=0:continue
        key=comparison_key(row)
        visual=visual_bucket(row,image_evidence)
        if not key or visual is None:continue
        key=key+visual
        if row['site']==BASELINE_SITE:
            if key not in baseline or row['price']<baseline[key]['price']:baseline[key]=row
        else:active.append((key,row))
    matches=[]
    for key,row in active:
        own=baseline.get(key)
        if own and row['price']<own['price']:
            difference=own['price']-row['price']
            matches.append({'brand':key[0],'model':model_of(row['title']),'dial_color':key[2],'year':key[3],'strap':key[4],'competitor':row,'baseline':own,'difference':difference,'difference_percent':round(100*difference/own['price'],1)})
    return {'baseline_models':len(baseline),'items':sorted(matches,key=lambda x:(-x['difference'],-x['difference_percent'],x['competitor']['url']))}

def same_product_items(rows,image_evidence=None,review_decisions=None):
    if image_evidence is not None:return reviewed_comparisons(rows,image_evidence,review_decisions or {})
    baseline={};competitors=[];grouped={}
    for row in rows:
        if row.get('missing_runs',0)>0 or row.get('status')=='possibly_removed' or not row.get('price') or row['price']<=0:continue
        brand=brand_of(row['title']);model=model_of(row['title']);dial=item_dial_color(row)
        if brand=='其他' or not model or not dial:continue
        normalized=re.sub(r'[^A-Z0-9]','',model.upper())
        if brand=='Panerai':normalized='PAM'+str(int(normalized[3:]))
        visual=visual_bucket(row,image_evidence)
        if visual is None:continue
        key=(brand,normalized,dial)+visual
        grouped.setdefault(key,[]).append(dict(row,strap=strap_of(row['title'])))
        if row['site']==BASELINE_SITE:baseline.setdefault(key,[]).append(row)
        else:competitors.append((key,row))
    items=[]
    for key,row in competitors:
        for own in baseline.get(key,[]):
            difference=own['price']-row['price']
            items.append({'brand':key[0],'model':model_of(row['title']),'dial_color':key[2],
                'competitor':dict(row,strap=strap_of(row['title'])),'baseline':dict(own,strap=strap_of(own['title'])),
                'difference':difference,'difference_percent':round(100*difference/own['price'],1)})
    groups=[]
    for key,listings in grouped.items():
        sites={x['site'] for x in listings}
        if len(sites)<2:continue
        listings=sorted(listings,key=lambda x:(x['price'],x['site'],x['url']))
        minimum=listings[0]['price'];maximum=listings[-1]['price']
        groups.append({'brand':key[0],'model':model_of(listings[0]['title']),'dial_color':key[2],
            'store_count':len(sites),'listing_count':len(listings),'minimum_price':minimum,'maximum_price':maximum,
            'spread':maximum-minimum,'listings':[dict(x,difference_from_lowest=x['price']-minimum,
                difference_percent=round(100*(x['price']-minimum)/minimum,1)) for x in listings]})
    review=[]
    if image_evidence is not None:
        for x in image_comparison_candidates(rows):
            check=dial_images.assessment(x,item_dial_color(x),image_evidence)
            if check['status']!='verified':review.append(dict(site=x['site'],url=x['url'],model=model_of(x['title']),image_url=x.get('image_url',''),reason=check['reason']))
    return {'image_review':review,'image_checked':image_evidence is not None,'baseline_models':len(baseline),'items':sorted(items,key=lambda x:(-x['difference'],x['model'],x['competitor']['url'],x['baseline']['url'])),
        'groups':sorted(groups,key=lambda g:(-g['spread'],g['brand'],g['model'],g['dial_color']))}


def reviewed_comparisons(rows,evidence,decisions):
    raw=same_product_items(rows)
    groups,items,pending,waiting=[],[],[],set()
    review_items={}
    for x in image_comparison_candidates(rows):
        result=dial_images.assessment(x,item_dial_color(x),evidence)
        if result['status']!='verified':
            review_items[(x['site'],x['url'])]=dict(site=x['site'],url=x['url'],model=model_of(x['title']),image_url=x.get('image_url',''),reason=result['reason'])
    for source in raw['groups']:
        clocks=[x for x in source['listings'] if x['site']==BASELINE_SITE]
        others=[x for x in source['listings'] if x['site']!=BASELINE_SITE]
        if not clocks:continue
        dial=source['dial_color'];states={}
        def state(b,o):return states[(b['url'],o['site'],o['url'])][1]
        for b in clocks:
            for o in others:
                value=comparison_reviews.pair_state(b,o,dial,model_of(b['title']),evidence,decisions)
                states[(b['url'],o['site'],o['url'])]=value
                key,choice,reason=value
                if choice=='pending':pending.append(comparison_reviews.review_details(key,b,o,dial,model_of(b['title']),reason))
                if choice=='analysing':waiting.add(key)
                if choice not in ('automatic','approved'):continue
                difference=b['price']-o['price']
                items.append(dict(brand=source['brand'],model=model_of(o['title']),dial_color=dial,
                    competitor=o,baseline=b,difference=difference,difference_percent=round(100*difference/b['price'],1),manual_review=choice=='approved'))
        clusters=[]
        for b in clocks:
            matches=[o for o in others if state(b,o) in ('automatic','approved')]
            if not matches:continue
            cluster=[b]+matches
            for i,previous in enumerate(clusters):
                merged=list({(x['site'],x['url']):x for x in previous+cluster}.values())
                if all(state(cb,co) in ('automatic','approved') for cb in merged if cb['site']==BASELINE_SITE for co in merged if co['site']!=BASELINE_SITE):
                    clusters[i]=merged;break
            else:clusters.append(cluster)
        for listings in clusters:
            listings=sorted(listings,key=lambda x:(x['price'],x['site'],x['url']))
            minimum=listings[0]['price'];maximum=listings[-1]['price']
            manual=sum(state(b,o)=='approved' for b in listings if b['site']==BASELINE_SITE for o in listings if o['site']!=BASELINE_SITE)
            groups.append(dict(brand=source['brand'],model=source['model'],dial_color=dial,
                store_count=len({x['site'] for x in listings}),listing_count=len(listings),minimum_price=minimum,
                maximum_price=maximum,spread=maximum-minimum,manual_review_count=manual,
                listings=[dict(x,difference_from_lowest=x['price']-minimum,difference_percent=round(100*(x['price']-minimum)/minimum,1)) for x in listings]))
    return dict(baseline_models=raw['baseline_models'],image_checked=True,image_review=list(review_items.values()),
        review_pairs=sorted(pending,key=lambda x:(x['model'],x['other']['site'],x['pair_key'])),image_pending_count=len(waiting),
        items=sorted(items,key=lambda x:(-x['difference'],x['model'],x['competitor']['url'],x['baseline']['url'])),
        groups=sorted(groups,key=lambda g:(-g['spread'],g['brand'],g['model'],g['dial_color'])))


def reviewed_low_prices(rows,evidence,decisions):
    baseline={};others=[]
    for row in rows:
        if row.get('missing_runs',0)>0 or row.get('status')=='possibly_removed' or not row.get('price') or row['price']<=0:continue
        key=comparison_key(row)
        if not key:continue
        if row['site']==BASELINE_SITE:baseline.setdefault(key,[]).append(row)
        else:others.append((key,row))
    matches=[]
    for key,row in others:
        candidates=[b for b in baseline.get(key,[]) if comparison_reviews.pair_state(b,row,key[2],model_of(b['title']),evidence,decisions)[1] in ('automatic','approved')]
        if not candidates:continue
        own=min(candidates,key=lambda x:x['price'])
        if row['price']>=own['price']:continue
        difference=own['price']-row['price']
        matches.append(dict(brand=key[0],model=model_of(row['title']),dial_color=key[2],year=key[3],strap=key[4],competitor=row,baseline=own,difference=difference,difference_percent=round(100*difference/own['price'],1)))
    return dict(baseline_models=len(baseline),items=sorted(matches,key=lambda x:(-x['difference'],-x['difference_percent'],x['competitor']['url'])))


def image_comparison_candidates(rows):
    # First narrow by source text; images never infer model, year or strap.
    groups=same_product_items(rows)['groups']
    candidates={}
    for g in groups:
        if not any(x['site']==BASELINE_SITE for x in g['listings']):continue
        for x in g['listings']:candidates[(x['site'],x['url'])]=x
    return list(candidates.values())

def analyse_current_dials(wait_for_crawl=False):
    if wait_for_crawl:
        for attempt in range(30):
            with connect() as c:
                busy=c.execute("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory' AND objid=68234016 AND granted)").fetchone()[0]
            if not busy:break
            time.sleep(20)
        else:
            logging.info('Dial image background check deferred while product crawler is active')
            return 0
    with connect() as c:
        fields=['site','url','title','price','image_url','missing_runs','status','brand','model','year','condition']
        rows=[dict(zip(fields,r)) for r in c.execute("SELECT site,url,title,price,image_url,missing_runs,status,brand,model,year,condition FROM watches WHERE price>0 AND missing_runs=0").fetchall()]
    count=dial_images.refresh_images(connect,image_comparison_candidates(rows))
    with connect() as c:
        evidence=dial_images.load_evidence(c,rows)
        decisions=comparison_reviews.load_decisions(c)
    result=same_product_items(rows,evidence,decisions)
    comparison_reviews.sync_pending(connect,result['review_pairs'])
    notifications=comparison_reviews.notify_pending(connect)
    logging.info('Dial images checked: %d; review pairs: %d; review notifications sent: %d, failed: %d',count,len(result['review_pairs']),notifications['sent'],notifications['failed'])
    return count


def change_of(old,item):
    if old is None:return 'new'
    before,previous_status,title,model,year,condition=old
    price=item['price']
    if before is not None and price is not None and price!=before:
        return 'price_down' if price<before else 'price_up'
    if previous_status=='possibly_removed':return 'returned'
    if (before,title,model,year,condition)!=(price,item['title'],item['model'],item['year'],item['condition']):return 'changed'
    return previous_status if previous_status in {'new','price_up','price_down','changed','returned'} else 'unchanged'

def product_images(soup,page_url):
    images={}
    def valid(raw):
        candidate=urllib.parse.urljoin(page_url,raw or '')
        parsed=urllib.parse.urlparse(candidate)
        if parsed.scheme not in ('http','https') or parsed.hostname!=urllib.parse.urlparse(page_url).hostname or not parsed.path.lower().startswith('/product/'):return ''
        return urllib.parse.urlunparse(parsed._replace(scheme='https'))
    for anchor in soup.find_all('a',href=True):
        link=urllib.parse.urljoin(page_url,anchor['href']).split('#')[0]
        photo=next((v for img in anchor.find_all('img') if (v:=valid(img.get('data-src') or img.get('src')))), '')
        if not photo:
            parent=anchor
            for _ in range(6):
                parent=parent.parent
                if parent is None:break
                photo=valid(parent.get('background'))
                if photo:break
        if photo and link not in images:images[link]=photo
    return images

def fetch_page(session,url):
    # Retry only idempotent public GETs; never bypass access-denied responses.
    delays=(3,8,15)
    for attempt in range(4):
        response=None
        try:
            response=session.get(url,timeout=(10,30),headers={'Connection':'close'} if attempt else {})
            response.raise_for_status()
            # Force the entire body to be received before parsing or writing data.
            response.content
            return response
        except requests.RequestException as exc:
            code=exc.response.status_code if exc.response is not None else None
            if code is not None and code not in (429,500,502,503,504):raise
            if attempt==3:raise
            delay=delays[attempt]
            if code==429 and exc.response is not None:
                retry_after=exc.response.headers.get('Retry-After','')
                if retry_after.isdigit():
                    # If a server requests a long cooldown, leave it for the next run.
                    if int(retry_after)>60:raise
                    delay=max(delay,int(retry_after))
            logging.warning('Page fetch interrupted (%s); retry %d/3 after %ss: %s',type(exc).__name__,attempt+1,delay,url)
            if response is not None:response.close()
            session.close()  # discard a broken pooled connection, keep session headers
            time.sleep(delay)

def extract(site,url,session):
    r=fetch_page(session,url);r.encoding=r.apparent_encoding
    soup=BeautifulSoup(r.text,'html.parser')
    images=product_images(soup,url)
    for x in soup(['script','style','noscript']):x.decompose()
    results={}
    for a in soup.find_all('a',href=True):
        title=a.get_text(' ',strip=True)
        if not 22<=len(title)<=550 or not any(k in title.upper() for k in BRANDS):continue
        link=urllib.parse.urljoin(url,a['href']).split('#')[0]
        if urllib.parse.urlparse(link).netloc!=urllib.parse.urlparse(url).netloc:continue
        if site=='雷達站':
            product_url=urllib.parse.urlparse(link)
            product_ids=urllib.parse.parse_qs(product_url.query).get('ID',[])
            if product_url.path.lower()!='/product_open.asp' or len(product_ids)!=1 or not product_ids[0].isdigit():continue
        node=a;context=''
        for _ in range(5):
            node=node.parent
            if node is None:break
            s=node.get_text(' ',strip=True)
            if re.search(r'售價\s*[:：]',s) and len(s)<2200:context=s;break
        if not context:continue
        p=re.search(r'售價\s*[:：]\s*(?:NT\$?\s*)?([\d,]+)\s*元?',context)
        price=int(p.group(1).replace(',','')) if p else None
        cond=re.search(r'(?:錶況|品項)\s*[:：]\s*(.{1,28}?)(?=\s+錶徑|\s+編號|\s+售價|$)',context)
        yr=re.search(r'(20\d{2})\s*年\s*(?:木紋|新式)?\s*(?:保卡|保單|保證書)',title) or re.search(r'(20\d{2})\s*年',title)
        results[link]={'site':site,'url':link,'title':title,'brand':brand_of(title),'model':model_of(title),'year':yr.group(1) if yr else '', 'condition':cond.group(1).strip() if cond else '', 'price':price,'price_text':str(price) if price is not None else '洽詢','image_url':images.get(link,'')}
    return list(results.values()),soup

def crawl():
    with connect() as lock:
        if not lock.execute('SELECT pg_try_advisory_lock(68234016)').fetchone()[0]:
            raise RuntimeError('Another crawl is already running')
        try:return _crawl()
        except Exception:
            with connect() as c:
                c.execute("UPDATE crawl_runs SET finished=now(),status='failed',errors=CASE WHEN errors='' THEN 'Crawler failed; see service logs' ELSE errors END WHERE status='running'")
            raise
        finally:lock.execute('SELECT pg_advisory_unlock(68234016)')

def record_missing(c,site,run_started):
    # Persist a snapshot on the second complete miss, in the same transaction
    # as the status update. Further misses do not create duplicate events.
    c.execute("""INSERT INTO removal_events(site,url,title,brand,model,year,condition,price,image_url,last_seen)
        SELECT site,url,title,brand,model,year,condition,price,image_url,last_seen
        FROM watches WHERE site=%s AND last_seen < %s AND missing_runs=1""",(site,run_started))
    c.execute("UPDATE watches SET missing_runs=missing_runs+1,status=CASE WHEN missing_runs+1>=2 THEN 'possibly_removed' ELSE status END WHERE site=%s AND last_seen < %s",(site,run_started))

def removal_window(raw=None):
    taipei=ZoneInfo('Asia/Taipei')
    day=date.fromisoformat(raw) if raw else datetime.now(taipei).date()
    start=datetime.combine(day,datetime.min.time(),tzinfo=taipei)
    return day.isoformat(),start,start+timedelta(days=1)

def listing_event_kind(old,baseline_run):
    if old is None:return None if baseline_run else 'listed'
    if old[1]=='possibly_removed':return 'returned'
    return None

def month_window(raw=None):
    taipei=ZoneInfo('Asia/Taipei')
    value=raw if raw is not None else datetime.now(taipei).strftime('%Y-%m')
    if not re.fullmatch(r'\d{4}-\d{2}',value):raise ValueError('Invalid month')
    year,month=map(int,value.split('-'))
    start=datetime(year,month,1,tzinfo=taipei)
    end=datetime(year+1,1,1,tzinfo=taipei) if month==12 else datetime(year,month+1,1,tzinfo=taipei)
    return value,start,end

def _crawl():
    init_db()
    with connect() as c:
        c.execute("UPDATE crawl_runs SET finished=now(),status='failed',errors='Previous crawler was interrupted' WHERE status='running'")
        runid=c.execute('INSERT INTO crawl_runs DEFAULT VALUES RETURNING id').fetchone()[0]
        run_started=c.execute('SELECT started FROM crawl_runs WHERE id=%s',(runid,)).fetchone()[0]
    total=0;errors=[]
    with requests.Session() as session:
        session.headers.update({'User-Agent':'WatchPriceMonitor/1.0 (public product listings; contact site owner for removal)'})
        for site,root in SITES.items():
            with connect() as c:baseline_run=not c.execute('SELECT EXISTS(SELECT 1 FROM watches WHERE site=%s AND source_order IS NOT NULL)',(site,)).fetchone()[0]
            queue=[root];visited=set();seen={};site_errors=[]
            maxpages=max(1,min(int(os.getenv('MAX_PAGES_PER_SITE','200')),200))
            while queue and len(visited)<maxpages:
                url=queue.pop(0)
                if url in visited:continue
                visited.add(url)
                try:rows,soup=extract(site,url,session)
                except Exception as e:
                    site_errors.append(f'{url}: {str(e)[:120]}');continue
                now=datetime.now(timezone.utc)
                with connect() as c:
                    previous={r[0]:r[1:] for r in c.execute('SELECT url,price,status,title,model,year,condition FROM watches WHERE site=%s AND url=ANY(%s)',(site,[x['url'] for x in rows])).fetchall()}
                    writes=[];price_changes=[];listing_changes=[]
                    for x in rows:
                        if x['url'] in seen:continue
                        seen[x['url']]=len(seen)+1
                        old=previous.get(x['url'])
                        change=change_of(old,x)
                        kind=listing_event_kind(old,baseline_run)
                        if kind:listing_changes.append((site,x['url'],kind,x['title'],x['brand'],x['model'],x['year'],x['condition'],x['price'],x['image_url'],now))
                        writes.append((x['site'],x['url'],x['title'],x['brand'],x['model'],x['year'],x['condition'],x['price'],x['price_text'],now,now,change,x['image_url']))
                        if x['price'] is not None and (old is None or old[0]!=x['price']):price_changes.append((site,x['url'],x['price'],now))
                    with c.cursor() as cur:
                        cur.executemany('''INSERT INTO watches(site,url,title,brand,model,year,condition,price,price_text,updated,last_seen,status,image_url,missing_runs) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0) ON CONFLICT(site,url) DO UPDATE SET activity_at=CASE WHEN watches.status='possibly_removed' OR ROW(watches.price,watches.title,watches.model,watches.year,watches.condition) IS DISTINCT FROM ROW(EXCLUDED.price,EXCLUDED.title,EXCLUDED.model,EXCLUDED.year,EXCLUDED.condition) THEN EXCLUDED.updated ELSE watches.activity_at END,title=EXCLUDED.title,brand=EXCLUDED.brand,model=EXCLUDED.model,year=EXCLUDED.year,condition=EXCLUDED.condition,price_changed_at=CASE WHEN watches.price IS NOT NULL AND EXCLUDED.price IS NOT NULL AND watches.price<>EXCLUDED.price THEN EXCLUDED.updated ELSE watches.price_changed_at END,price=EXCLUDED.price,price_text=EXCLUDED.price_text,updated=EXCLUDED.updated,last_seen=EXCLUDED.last_seen,status=EXCLUDED.status,image_url=COALESCE(NULLIF(EXCLUDED.image_url,''),watches.image_url),missing_runs=0''',writes)
                        cur.executemany('INSERT INTO history(site,url,price,checked) VALUES(%s,%s,%s,%s)',price_changes)
                        cur.executemany('INSERT INTO listing_events(site,url,event_type,title,brand,model,year,condition,price,image_url,detected_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',listing_changes)
                for a in soup.find_all('a',href=True):
                    if re.fullmatch(r'\d{1,3}',a.get_text(' ',strip=True)):
                        nxt=urllib.parse.urljoin(url,a['href']).split('#')[0]
                        if urllib.parse.urlparse(nxt).netloc==urllib.parse.urlparse(root).netloc and nxt not in visited and nxt not in queue:queue.append(nxt)
                time.sleep(float(os.getenv('CRAWL_DELAY_SECONDS','2')))
            # Avoid false delisting when pagination is incomplete or site blocks scraping.
            total+=len(seen)
            logging.info('%s: %d unique products, %d pages, %d queued',site,len(seen),len(visited),len(queue))
            if not seen:site_errors.append('No products found; check site parser or access restrictions')
            if queue:site_errors.append('Page limit reached; inventory coverage is incomplete')
            if site_errors:errors.extend(f'{site}: {e}' for e in site_errors[:3])
            if not site_errors and not queue and seen:
                with connect() as c:
                    c.execute("""UPDATE watches w SET source_order=listing.position FROM
                        unnest(%s::text[]) WITH ORDINALITY AS listing(url,position)
                        WHERE w.site=%s AND w.url=listing.url""",(list(seen),site))
                    record_missing(c,site,run_started)
    with connect() as c:
        c.execute('UPDATE crawl_runs SET finished=now(),status=%s,count=%s,errors=%s WHERE id=%s',('partial' if errors else 'completed',total,'; '.join(errors),runid))
    try:analyse_current_dials()
    except Exception:logging.exception('Dial image checks incomplete; unverified products excluded from comparisons')
    if errors:raise RuntimeError('Crawl incomplete: '+'; '.join(errors))
    try:
        result=push.notify_low_prices(connect,lower_price_with_images)
        logging.info('Low-price notifications: %d sent, %d failed',result['sent'],result['failed'])
    except Exception:logging.warning('Low-price notification check failed; will retry after next complete crawl')
    try:
        result=push.notify_market_events(connect)
        logging.info('Market-event notifications: %d sent, %d failed',result['sent'],result['failed'])
    except Exception:logging.exception('Market-event notification check failed; will retry after next complete crawl')
    return total

@app.get('/manifest.webmanifest')
def manifest():
    data={'id':'/','name':'鐘點站名錶監控','short_name':'鐘點站監控','lang':'zh-TW','start_url':'/','scope':'/','display':'standalone','background_color':'#152337','theme_color':'#152337','icons':[
        {'src':f'/app-icon-{size}.png','sizes':f'{size}x{size}','type':'image/png','purpose':'any maskable'} for size in [192,512]]}
    return Response(json.dumps(data,ensure_ascii=False),mimetype='application/manifest+json',headers={'Cache-Control':'no-cache'})

@app.get('/app-icon-<int:size>.png')
def app_icon(size):
    if size not in ICONS:return Response('Not found',404)
    return Response(base64.b64decode(ICONS[size]),mimetype='image/png',headers={'Cache-Control':'public, max-age=86400'})

@app.get('/service-worker.js')
def service_worker():
    return Response(SERVICE_WORKER,mimetype='application/javascript',headers={'Cache-Control':'no-cache','Service-Worker-Allowed':'/'})

@app.after_request
def private_data_cache(response):
    if request.path=='/' or request.path.startswith('/api/'):
        response.headers['Cache-Control']='private, no-store'
    return response

@app.get('/health')
def health():return {'ok':True}

@app.get('/ready')
def ready():
    try:
        with connect() as c:c.execute('SELECT 1 FROM watches LIMIT 1')
        return {'ok':True,'database':'connected'}
    except Exception:
        app.logger.exception('Database readiness failed')
        return {'ok':False,'database':'unavailable'},503

@app.get('/')
def home():return send_file('index.html' if auth_ok() else 'login.html')

@app.post('/api/login')
def login():
    return account_login()

from market_trends import install as install_market_trends
install_market_trends(app, connect, protected)

@app.get('/market-trends.js')
@protected
def market_script():
    return send_file('market_trends.js')

@app.get('/api/watches')
@protected
def watches():
    with connect() as c:
        rows=c.execute("SELECT site,url,title,brand,model,year,condition,price,price_text,updated,status,image_url,source_order,price_changed_at,missing_runs,(SELECT e.detected_at FROM listing_events e WHERE e.site=watches.site AND e.url=watches.url AND e.event_type='listed' ORDER BY e.detected_at LIMIT 1) AS listed_at,GREATEST(activity_at,price_changed_at,first_seen,(SELECT max(e.detected_at) FROM listing_events e WHERE e.site=watches.site AND e.url=watches.url AND e.event_type IN ('listed','returned'))) AS last_activity_at,(SELECT h.price FROM history h WHERE h.site=watches.site AND h.url=watches.url AND h.price IS NOT NULL AND h.price<>watches.price ORDER BY h.checked DESC,h.id DESC LIMIT 1) AS previous_price,(SELECT COALESCE(jsonb_agg(jsonb_build_object('old_price',p.old_price,'price',p.price,'checked',p.checked) ORDER BY p.checked DESC,p.id DESC),'[]'::jsonb) FROM (SELECT h.id,h.price,h.checked,lag(h.price) OVER (ORDER BY h.checked,h.id) AS old_price FROM history h WHERE h.site=watches.site AND h.url=watches.url) p WHERE p.old_price IS NOT NULL AND p.price IS NOT NULL AND p.old_price<>p.price) AS price_changes FROM watches ORDER BY price_changed_at DESC NULLS LAST,CASE site WHEN '鐘點站' THEN 0 WHEN '永生' THEN 1 WHEN '玩錶舍' THEN 2 WHEN '雷達站' THEN 3 ELSE 4 END,source_order NULLS LAST,url LIMIT 20000").fetchall()
    return jsonify([dict(zip(['site','url','title','brand','model','year','condition','price','price_text','updated','status','image_url','source_order','price_changed_at','missing_runs','listed_at','last_activity_at','previous_price','price_changes'],[v.isoformat() if isinstance(v,datetime) else v for v in r])) for r in rows])

@app.get('/api/status')
@protected
def status():
    with connect() as c:r=c.execute('SELECT finished,status,count,errors FROM crawl_runs ORDER BY id DESC LIMIT 1').fetchone()
    return jsonify({'running':bool(r and r[0] is None),'last_run':r[0].isoformat() if r and r[0] else None,'count':r[2] if r else 0,'error':r[3] if r else None,'run_status':r[1] if r else 'never'})

@app.get('/api/comparisons')
@protected
def comparisons():
    with connect() as c:
        records=c.execute('SELECT site,url,title,brand,model,year,condition,price,image_url,updated,status,missing_runs FROM watches WHERE price > 0 AND missing_runs=0').fetchall()
    fields=['site','url','title','brand','model','year','condition','price','image_url','updated','status','missing_runs']
    rows=[dict(zip(fields,[v.isoformat() if isinstance(v,datetime) else v for v in r])) for r in records]
    with connect() as c:
        evidence=dial_images.load_evidence(c,rows)
        decisions=comparison_reviews.load_decisions(c)
    return jsonify(same_product_items(rows,evidence,decisions))

@app.get('/comparison-reviews.js')
@protected
def comparison_review_script():return send_file('comparison_reviews.js')

@app.post('/api/comparison-review')
@protected
def decide_comparison():
    if request.headers.get('X-Watch-Monitor')!='1':return jsonify(error='Missing request header'),403
    body=request.get_json(silent=True)
    if not isinstance(body,dict) or body.get('decision') not in ('approved','rejected'):return jsonify(error='請選擇需要比價或不需要'),400
    if not all(isinstance(body.get(k),str) and len(body[k])<=4096 for k in ('pair_key','baseline_url','other_site','other_url')):return jsonify(error='比價組合資料不完整'),400
    with connect() as c:
        fields=['site','url','title','brand','model','year','condition','price','image_url']
        records=c.execute("SELECT site,url,title,brand,model,year,condition,price,image_url FROM watches WHERE missing_runs=0 AND price>0 AND ((site=%s AND url=%s) OR (site=%s AND url=%s))",(BASELINE_SITE,body['baseline_url'],body['other_site'],body['other_url'])).fetchall()
        rows=[dict(zip(fields,r)) for r in records]
        b=next((x for x in rows if x['site']==BASELINE_SITE and x['url']==body['baseline_url']),None)
        o=next((x for x in rows if x['site']==body['other_site'] and x['url']==body['other_url']),None)
        if not b or not o or o['site']==BASELINE_SITE:return jsonify(error='商品已變更或無法比價，請重新整理'),409
        raw=same_product_items(rows)
        if not raw['groups'] or not raw['items']:return jsonify(error='型號或面盤文字已變更，請重新確認'),409
        dial=item_dial_color(b);model=model_of(b['title']);evidence=dial_images.load_evidence(c,rows)
        key=comparison_reviews.review_key(b,o,dial,model,evidence)
        if key!=body['pair_key']:return jsonify(error='商品圖片或資料已變更，請重新確認'),409
        details=comparison_reviews.review_details(key,b,o,dial,model,'使用者確認')
        comparison_reviews.save_decision(c,details,body['decision'])
    return jsonify(saved=True,decision=body['decision'])

@app.get('/api/removals')
@protected
def removals():
    try:day,start,end=removal_window(request.args.get('date'))
    except ValueError:return jsonify({'error':'日期格式須為 YYYY-MM-DD'}),400
    with connect() as c:
        records=c.execute("""SELECT e.site,e.url,e.title,e.brand,e.model,e.year,e.condition,e.price,e.image_url,e.last_seen,e.detected_at,
            COALESCE(w.missing_runs=0,false) AS returned
            FROM removal_events e LEFT JOIN watches w ON w.site=e.site AND w.url=e.url
            WHERE e.detected_at >= %s AND e.detected_at < %s AND NOT EXISTS (
                SELECT 1 FROM listing_events later
                WHERE later.site=e.site AND later.event_type IN ('listed','returned') AND later.detected_at>e.detected_at
                AND (later.url=e.url OR (
                    NULLIF(btrim(e.title),'') IS NOT NULL AND later.title=e.title
                    AND ROW(later.brand,later.model,later.year,later.condition,later.price,later.image_url)
                        IS NOT DISTINCT FROM ROW(e.brand,e.model,e.year,e.condition,e.price,e.image_url)
                )))
            ORDER BY e.detected_at DESC,e.id DESC""",(start,end)).fetchall()
    fields=['site','url','title','brand','model','year','condition','price','image_url','last_seen','detected_at','returned']
    groups={site:[] for site in SITES}
    for record in records:
        row=dict(zip(fields,[v.isoformat() if isinstance(v,datetime) else v for v in record]))
        groups.setdefault(row['site'],[]).append(row)
    return jsonify({'date':day,'timezone':'Asia/Taipei','count':len(records),'groups':[{'site':site,'count':len(items),'items':items} for site,items in groups.items()]})

@app.get('/api/monthly-events')
@protected
def monthly_events():
    try:month,start,end=month_window(request.args.get('month'))
    except ValueError:return jsonify({'error':'月份格式須為 YYYY-MM'}),400
    with connect() as c:
        records=c.execute("""SELECT e.site,e.url,e.event_type,e.title,e.brand,e.model,e.year,e.condition,e.price,e.image_url,e.detected_at,e.snapshot_source
            FROM listing_events e WHERE e.event_type IN ('listed','returned') AND e.detected_at >= %s AND e.detected_at < %s
            UNION ALL
            SELECT e.site,e.url,'removed',e.title,e.brand,e.model,e.year,e.condition,e.price,e.image_url,e.detected_at,'observed'
            FROM removal_events e WHERE e.detected_at >= %s AND e.detected_at < %s AND NOT EXISTS (
                SELECT 1 FROM listing_events later
                WHERE later.site=e.site AND later.event_type IN ('listed','returned') AND later.detected_at>e.detected_at
                AND (later.url=e.url OR (
                    NULLIF(btrim(e.title),'') IS NOT NULL AND later.title=e.title
                    AND ROW(later.brand,later.model,later.year,later.condition,later.price,later.image_url)
                        IS NOT DISTINCT FROM ROW(e.brand,e.model,e.year,e.condition,e.price,e.image_url)
                )))
            ORDER BY 11 DESC,1,2""",(start,end,start,end)).fetchall()
    fields=['site','url','event_type','title','brand','model','year','condition','price','image_url','detected_at','snapshot_source']
    groups={site:[] for site in SITES}
    for record in records:
        item=dict(zip(fields,[v.isoformat() if isinstance(v,datetime) else v for v in record]))
        groups.setdefault(item['site'],[]).append(item)
    return jsonify({'month':month,'timezone':'Asia/Taipei','count':len(records),'groups':[
        {'site':site,'counts':{kind:sum(x['event_type']==kind for x in items) for kind in ['listed','removed','returned']},'items':items}
        for site,items in groups.items()]})

@app.get('/api/clock-daily')
@protected
def clock_daily():
    try:day,start,end=removal_window(request.args.get('date'))
    except ValueError:return jsonify({'error':'日期格式須為 YYYY-MM-DD'}),400
    with connect() as c:
        listed=c.execute("SELECT url,title,brand,model,year,condition,price,image_url,detected_at FROM listing_events WHERE site='鐘點站' AND event_type='listed' AND detected_at >= %s AND detected_at < %s ORDER BY detected_at DESC,id DESC",(start,end)).fetchall()
        changed=c.execute("""WITH changes AS (
            SELECT url,price,checked,id,lag(price) OVER (PARTITION BY site,url ORDER BY checked,id) AS old_price
            FROM history WHERE site='鐘點站')
            SELECT h.url,w.title,w.brand,w.model,w.year,w.condition,h.price,w.image_url,h.checked,h.old_price
            FROM changes h LEFT JOIN watches w ON w.site='鐘點站' AND w.url=h.url
            WHERE h.checked >= %s AND h.checked < %s AND h.old_price IS NOT NULL AND h.price <> h.old_price
            ORDER BY h.checked DESC,h.id DESC""",(start,end)).fetchall()
    fields=['url','title','brand','model','year','condition','price','image_url','detected_at']
    def encode(row,keys):return dict(zip(keys,[v.isoformat() if isinstance(v,datetime) else v for v in row]))
    new=[encode(r,fields) for r in listed]
    changes=[encode(r,fields+['old_price']) for r in changed]
    return jsonify({'date':day,'timezone':'Asia/Taipei','listed':new,'changes':changes,
        'counts':{'listed':len(new),'price_events':len(changes),'price_products':len({r['url'] for r in changes}),'up':sum(r['price']>r['old_price'] for r in changes),'down':sum(r['price']<r['old_price'] for r in changes)}})

@app.get('/api/push/config')
@protected
def push_config():return jsonify({'enabled':push.configured(),'publicKey':os.getenv('VAPID_PUBLIC_KEY','')})

@app.post('/api/push/subscribe')
@protected
def push_subscribe():
    if request.headers.get('X-Watch-Monitor')!='1':return jsonify({'error':'Missing request header'}),403
    if not push.configured():return jsonify({'error':'通知服務尚未就緒'}),503
    try:subscription=push.validate_subscription(request.get_json(silent=True))
    except (ValueError,TypeError):return jsonify({'error':'無效的手機推播訂閱資料'}),400
    sid=push.subscription_id(subscription['endpoint'])
    with connect() as c:
        c.execute('INSERT INTO push_subscriptions(id,subscription) VALUES(%s,%s::jsonb) ON CONFLICT(id) DO UPDATE SET subscription=EXCLUDED.subscription,updated_at=now()',(sid,json.dumps(subscription)))
        push.initialize_event_cursor(c,sid)
    return jsonify({'ok':True})

@app.post('/api/push/unsubscribe')
@protected
def push_unsubscribe():
    if request.headers.get('X-Watch-Monitor')!='1':return jsonify({'error':'Missing request header'}),403
    body=request.get_json(silent=True) or {};endpoint=body.get('endpoint') if isinstance(body,dict) else None
    if not isinstance(endpoint,str) or len(endpoint)>4096:return jsonify({'error':'無效資料'}),400
    with connect() as c:c.execute('DELETE FROM push_subscriptions WHERE id=%s',(push.subscription_id(endpoint),))
    return jsonify({'ok':True})

@app.post('/api/push/test')
@protected
def push_test():
    if request.headers.get('X-Watch-Monitor')!='1':return jsonify({'error':'Missing request header'}),403
    if not push.configured():return jsonify({'error':'通知服務尚未就緒'}),503
    body=request.get_json(silent=True) or {};endpoint=body.get('endpoint') if isinstance(body,dict) else None
    if not isinstance(endpoint,str) or len(endpoint)>4096:return jsonify({'error':'無效資料'}),400
    with connect() as c:record=c.execute('SELECT subscription FROM push_subscriptions WHERE id=%s',(push.subscription_id(endpoint),)).fetchone()
    if not record:return jsonify({'error':'請先啟用此裝置通知'}),404
    try:push.send(record[0],{'title':'鐘點站通知測試成功','body':'商品通知已啟用；完整爬取後檢查低於鐘點站、同業上架與價格變動。','url':'/#comparisonSection','tag':'notification-test'})
    except Exception:return jsonify({'error':'測試通知送出失敗，請重新啟用通知後再試'}),502
    return jsonify({'ok':True})

@app.get('/api/history')
@protected
def history():
    url=request.args.get('url','')
    with connect() as c:r=c.execute('SELECT site,url,price,checked FROM history WHERE url=%s ORDER BY checked DESC LIMIT 100',(url,)).fetchall()
    return jsonify([dict(site=x[0],url=x[1],price=x[2],checked=x[3].isoformat()) for x in r])

@app.post('/api/crawl')
@protected
def manual():
    if request.headers.get('X-Watch-Monitor') != '1':return jsonify({'error':'Missing request header'}),403
    with connect() as c:
        running=c.execute("SELECT 1 FROM pg_locks WHERE locktype='advisory' AND objid=68234016 AND granted").fetchone()
    if running:return jsonify({'error':'更新已在執行中'}),409
    subprocess.Popen([sys.executable,os.path.abspath(__file__),'crawl-products'],cwd=app.root_path)
    return jsonify({'started':True}),202

if __name__=='__main__':
    import sys
    if len(sys.argv)>1 and sys.argv[1]=='analyze-dials':
        try:
            for _ in range(3):
                if analyse_current_dials(wait_for_crawl=True)<120:break
        except Exception:logging.exception('Dial image background check failed')
    elif len(sys.argv)>1 and sys.argv[1] in ('market','market-force'):
        from market_trends import refresh_if_due
        try:refresh_if_due(connect,force=sys.argv[1]=='market-force',brand_slug=sys.argv[2] if len(sys.argv)>2 else None)
        except Exception:logging.exception('VIP Station update failed; retained previous snapshot')
    elif len(sys.argv)>1 and sys.argv[1] in ('crawl','crawl-products'):
        market_job=None
        # Scheduled noon work runs separately; the product button never starts it.
        if sys.argv[1]=='crawl' and datetime.now(ZoneInfo('Asia/Taipei')).hour==12:
            market_job=subprocess.Popen([sys.executable,os.path.abspath(__file__),'market'],cwd=app.root_path)
        try:print('Extracted rows:',crawl())
        finally:
            if market_job:market_job.wait()
    elif len(sys.argv)>1 and sys.argv[1]=='init':init_db()
    else:app.run(host='0.0.0.0',port=int(os.getenv('PORT','10000')))

# One background cache fill on web startup; advisory lock prevents duplicate workers.
if __name__=='app' and os.environ.get('DATABASE_URL'):
    subprocess.Popen([sys.executable,os.path.abspath(__file__),'analyze-dials'],cwd=app.root_path)
