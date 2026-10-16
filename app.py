import os, re, json, time, hmac, hashlib, logging, urllib.parse, subprocess, sys
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, request, jsonify, Response, send_file
import requests, psycopg
from bs4 import BeautifulSoup

app=Flask(__name__)
logging.basicConfig(level=logging.INFO)
SITES={'永生':'https://www.egps.com.tw/','玩錶舍':'https://www.playwatch.com.tw/','雷達站':'https://www.rdwatch.com.tw/'}
BRANDS={'ROLEX':'Rolex','PATEK PHILIPPE':'Patek Philippe','AUDEMARS PIGUET':'Audemars Piguet','OMEGA':'Omega','CARTIER':'Cartier','IWC':'IWC','HUBLOT':'Hublot','GRAND SEIKO':'Grand Seiko','CHOPARD':'Chopard','ZENITH':'Zenith','RICHARD MILLE':'Richard Mille','VACHERON CONSTANTIN':'Vacheron Constantin','JAEGER':'Jaeger-LeCoultre','FRANCK MULLER':'Franck Muller','TUDOR':'Tudor','PANERAI':'Panerai','BVLGARI':'Bvlgari','朗格':'A. Lange & Söhne'}
MODEL=re.compile(r'(?<![A-Za-z0-9])(?:[A-Z]{0,5}\d{3,8}[A-Z]{0,5}(?:[./-][A-Z0-9]{1,12}){0,4}|\d{2,6}[./-][A-Z0-9]{2,10}(?:[./-][A-Z0-9]{2,12}){0,3})(?![A-Za-z0-9])',re.I)

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

def auth_ok():
    secret=os.environ.get('ADMIN_PASSWORD','')
    supplied=request.authorization.password if request.authorization and request.authorization.type.lower()=='basic' else ''
    return bool(secret) and hmac.compare_digest(supplied,secret)

def protected(fn):
    @wraps(fn)
    def inner(*a,**kw):
        if not auth_ok():return Response('請輸入管理員密碼',401,{'WWW-Authenticate':'Basic realm="Watch Monitor"'})
        return fn(*a,**kw)
    return inner

def brand_of(t):
    u=t.upper()
    return next((v for k,v in BRANDS.items() if k in u),'其他')

def model_of(t):
    for m in MODEL.finditer(t):
        s=m.group().upper()
        if not re.fullmatch(r'20\d{2}|\d{2,3}MM',s):return s
    return ''

def change_of(old,item):
    if old is None:return 'new'
    before,previous_status,title,model,year,condition=old
    price=item['price']
    if before is not None and price is not None and price!=before:
        return 'price_down' if price<before else 'price_up'
    if previous_status=='possibly_removed':return 'returned'
    if (before,title,model,year,condition)!=(price,item['title'],item['model'],item['year'],item['condition']):return 'changed'
    return 'unchanged'

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

def extract(site,url,session):
    r=session.get(url,timeout=25);r.raise_for_status();r.encoding=r.apparent_encoding
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
            queue=[root];visited=set();seen=set();site_errors=[]
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
                    writes=[];price_changes=[]
                    for x in rows:
                        if x['url'] in seen:continue
                        seen.add(x['url'])
                        old=previous.get(x['url'])
                        change=change_of(old,x)
                        writes.append((x['site'],x['url'],x['title'],x['brand'],x['model'],x['year'],x['condition'],x['price'],x['price_text'],now,now,change,x['image_url']))
                        if x['price'] is not None and (old is None or old[0]!=x['price']):price_changes.append((site,x['url'],x['price'],now))
                    with c.cursor() as cur:
                        cur.executemany('''INSERT INTO watches(site,url,title,brand,model,year,condition,price,price_text,updated,last_seen,status,image_url,missing_runs) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0) ON CONFLICT(site,url) DO UPDATE SET title=EXCLUDED.title,brand=EXCLUDED.brand,model=EXCLUDED.model,year=EXCLUDED.year,condition=EXCLUDED.condition,price=EXCLUDED.price,price_text=EXCLUDED.price_text,updated=EXCLUDED.updated,last_seen=EXCLUDED.last_seen,status=EXCLUDED.status,image_url=COALESCE(NULLIF(EXCLUDED.image_url,''),watches.image_url),missing_runs=0''',writes)
                        cur.executemany('INSERT INTO history(site,url,price,checked) VALUES(%s,%s,%s,%s)',price_changes)
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
                    c.execute("UPDATE watches SET missing_runs=missing_runs+1,status=CASE WHEN missing_runs+1>=2 THEN 'possibly_removed' ELSE status END WHERE site=%s AND last_seen < %s",(site,run_started))
    with connect() as c:
        c.execute('UPDATE crawl_runs SET finished=now(),status=%s,count=%s,errors=%s WHERE id=%s',('partial' if errors else 'completed',total,'; '.join(errors),runid))
    if errors:raise RuntimeError('Crawl incomplete: '+'; '.join(errors))
    return total

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
@protected
def home():return send_file('index.html')

@app.get('/api/watches')
@protected
def watches():
    with connect() as c:
        rows=c.execute('SELECT site,url,title,brand,model,year,condition,price,price_text,updated,status,image_url FROM watches ORDER BY updated DESC LIMIT 20000').fetchall()
    return jsonify([dict(zip(['site','url','title','brand','model','year','condition','price','price_text','updated','status','image_url'],[v.isoformat() if isinstance(v,datetime) else v for v in r])) for r in rows])

@app.get('/api/status')
@protected
def status():
    with connect() as c:r=c.execute('SELECT finished,status,count,errors FROM crawl_runs ORDER BY id DESC LIMIT 1').fetchone()
    return jsonify({'running':bool(r and r[0] is None),'last_run':r[0].isoformat() if r and r[0] else None,'count':r[2] if r else 0,'error':r[3] if r else None,'run_status':r[1] if r else 'never'})

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
