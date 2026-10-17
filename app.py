import os, re, json, time, hmac, hashlib, logging, urllib.parse, subprocess, sys
from datetime import datetime, timezone, date, timedelta
from zoneinfo import ZoneInfo
from functools import wraps
from flask import Flask, request, jsonify, Response, send_file, session
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

def auth_ok():
    secret=os.environ.get('ADMIN_PASSWORD','')
    if not secret:return False
    credentials=request.authorization
    if credentials and credentials.type.lower()=='basic':
        if hmac.compare_digest((credentials.username or '').encode('utf-8'),b'HS') and hmac.compare_digest((credentials.password or '').encode('utf-8'),secret.encode('utf-8')):return True
    return bool(app.secret_key and session.get('user')=='HS' and hmac.compare_digest(session.get('auth_version',''),session_auth_version()))

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
    colors=r'煙燻綠|煙燻藍|煙燻灰|天藍|蒂芙尼藍|TIFFANY藍|冰藍|淺藍|深藍|亮藍|海軍藍|午夜藍|薄荷綠|橄欖綠|墨綠|深綠|淺綠|綠松石|香檳金|香檳|玫瑰金|巧克力|咖啡|棕|褐|黑|白|銀|金|灰|藍|綠|紅|粉紅|粉|紫|黃|橘|橙'
    pattern=r'('+colors+r')(?:色)?(?:太陽放射紋|太陽紋|放射紋|波紋|條紋|巴黎釘紋|旭日紋|格紋|鏤空|漆|珍珠母貝|貝殼)?(?:面盤|錶盤|錶面|面)(?!盤?時標|框|圈)'
    found={m.group(1) for m in re.finditer(pattern,title)}
    # Distinct special dials must not collapse into a plain base color.
    if re.search(r'熊貓|漸層|漸藍|雙色|多色|彩色|滿天星|袖扣|項鍊|錶盒',title):return ''
    if re.search(r'漸變(?!煙燻)',title):return ''
    if len(found)!=1:return ''
    color=found.pop()
    return {'粉':'粉紅','香檳':'香檳金','褐':'棕','橙':'橘'}.get(color,color)

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

def comparison_attributes(item):
    title=item.get('title') or ''
    years=set(re.findall(r'(20\d{2})\s*年\s*(?:(?:新式|木紋|電子)\s*)*(?:保卡|保單|保證書)',title))
    return dial_color_of(title),(next(iter(years)) if len(years)==1 else ''),strap_of(title)

def comparison_key(item):
    brand=brand_of(item['title'])
    reference=model_of(item['title'])
    if not reference or brand=='其他':return None
    normalized=re.sub(r'[^A-Z0-9]','',reference.upper())
    if brand=='Panerai':normalized='PAM'+str(int(normalized[3:]))
    attributes=comparison_attributes(item)
    if not all(attributes):return None
    return (brand,normalized)+attributes

def lower_price_items(rows):
    baseline={};active=[]
    for row in rows:
        if row.get('missing_runs',0)>0 or row.get('status')=='possibly_removed' or not row.get('price') or row['price']<=0:continue
        key=comparison_key(row)
        if not key:continue
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
    if errors:raise RuntimeError('Crawl incomplete: '+'; '.join(errors))
    try:
        result=push.notify_low_prices(connect,lower_price_items)
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
    if request.headers.get('X-Watch-Monitor')!='1':return jsonify({'error':'Missing request header'}),403
    if not app.secret_key:return jsonify({'error':'登入服務正在更新，請稍後重試'}),503
    body=request.get_json(silent=True) or {}
    if not isinstance(body,dict):return jsonify({'error':'帳號或密碼不正確'}),401
    username=body.get('username');password=body.get('password');secret=os.getenv('ADMIN_PASSWORD','')
    if not isinstance(username,str) or not isinstance(password,str) or not secret or len(username)>100 or len(password)>256:return jsonify({'error':'帳號或密碼不正確'}),401
    if not hmac.compare_digest(username.encode(),b'HS') or not hmac.compare_digest(password.encode(),secret.encode()):return jsonify({'error':'帳號或密碼不正確'}),401
    session.clear();session.permanent=True;session['user']='HS';session['auth_version']=session_auth_version()
    return jsonify({'ok':True})

@app.get('/api/watches')
@protected
def watches():
    with connect() as c:
        rows=c.execute("SELECT site,url,title,brand,model,year,condition,price,price_text,updated,status,image_url,source_order,price_changed_at,missing_runs,(SELECT e.detected_at FROM listing_events e WHERE e.site=watches.site AND e.url=watches.url AND e.event_type='listed' ORDER BY e.detected_at LIMIT 1) AS listed_at,GREATEST(activity_at,price_changed_at,first_seen,(SELECT max(e.detected_at) FROM listing_events e WHERE e.site=watches.site AND e.url=watches.url AND e.event_type IN ('listed','returned'))) AS last_activity_at FROM watches ORDER BY price_changed_at DESC NULLS LAST,CASE site WHEN '鐘點站' THEN 0 WHEN '永生' THEN 1 WHEN '玩錶舍' THEN 2 WHEN '雷達站' THEN 3 ELSE 4 END,source_order NULLS LAST,url LIMIT 20000").fetchall()
    return jsonify([dict(zip(['site','url','title','brand','model','year','condition','price','price_text','updated','status','image_url','source_order','price_changed_at','missing_runs','listed_at','last_activity_at'],[v.isoformat() if isinstance(v,datetime) else v for v in r])) for r in rows])

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
    return jsonify(lower_price_items(rows))

@app.get('/api/removals')
@protected
def removals():
    try:day,start,end=removal_window(request.args.get('date'))
    except ValueError:return jsonify({'error':'日期格式須為 YYYY-MM-DD'}),400
    with connect() as c:
        records=c.execute("""SELECT e.site,e.url,e.title,e.brand,e.model,e.year,e.condition,e.price,e.image_url,e.last_seen,e.detected_at,
            COALESCE(w.missing_runs=0,false) AS returned
            FROM removal_events e LEFT JOIN watches w ON w.site=e.site AND w.url=e.url
            WHERE e.detected_at >= %s AND e.detected_at < %s
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
            FROM removal_events e WHERE e.detected_at >= %s AND e.detected_at < %s
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
    subprocess.Popen([sys.executable,os.path.abspath(__file__),'crawl'],cwd=app.root_path)
    return jsonify({'started':True}),202

if __name__=='__main__':
    import sys
    if len(sys.argv)>1 and sys.argv[1]=='crawl':print('Extracted rows:',crawl())
    elif len(sys.argv)>1 and sys.argv[1]=='init':init_db()
    else:app.run(host='0.0.0.0',port=int(os.getenv('PORT','10000')))
