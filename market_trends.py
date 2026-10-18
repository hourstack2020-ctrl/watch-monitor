"""Daily, per-listing public HKD quotes from VIP Station's pre-owned catalogue."""
import hashlib
import json
import logging
import subprocess
import sys
import os
import re
import time
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote
import requests
from flask import jsonify, request

SOURCE = 'https://www.vipstation.com.hk/tc/watches'
BRANDS = {'PP':'Patek Philippe 百達翡麗','ROLEX':'Rolex 勞力士','RICHARD MILLE':'Richard Mille 理查德米勒','AP':'Audemars Piguet 愛彼'}
TZ = ZoneInfo('Asia/Taipei')


def variable(html, name):
    match = re.search(r'\bvar\s+' + re.escape(name) + r'\s*=\s*', html)
    if not match:
        raise ValueError('來源資料格式變更：' + name)
    return json.JSONDecoder().raw_decode(html[match.end():])[0]


def normalize(item, detail=None):
    brand = BRANDS.get(item.get('ST_ITEMGROUP'))
    title = item.get('ST_NAME', '')
    price = item.get('NO_PRICE')
    if not brand or item.get('NO_ISSTOCK') != 1 or item.get('ST_PRICETIPS'):
        return None
    if not isinstance(price, (float, int)) or isinstance(price, bool) or price <= 0:
        return None
    if item.get('ST_CURR') not in ('', None, 'HKD'):
        raise ValueError('來源幣值不是 HKD，保留上次資料')
    if detail is None:
        model, series = '', ''
    else:
        if detail.get('ST_CODE') != item.get('ST_CODE'):
            raise ValueError('商品詳細頁編號不符，保留上次資料')
        fields = {x['ST_KEY']:x.get('ST_VALUE','') for x in detail.get('ST_PRODETAILS', [])}
        brand = str(detail.get('ST_WEB_SUBCATALOG') or '').strip()
        series = str(fields.get('系列') or '').strip() or '來源未提供系列'
        model = str(fields.get('型號') or detail.get('ST_TYPE') or '').strip()
        if not brand or not model:
            raise ValueError('來源未提供品牌或型號')
    variant = re.sub(r'\s+', '', unicodedata.normalize('NFKC', title)).upper()
    image = item.get('ST_IMG', '')
    if not image.startswith('https://img.vipstation.com.hk/'):
        image = ''
    slug = item.get('ST_WEB_NAME')
    code = str(item.get('ST_CODE') or '')
    if not code or not slug:
        return None
    return dict(source_id=code, variant_key=hashlib.sha256(variant.encode()).hexdigest(),
                brand=brand, series=series, model=model, title=title, price=round(price),
                image_url=image, url='https://www.vipstation.com.hk/tc/item/' + quote(slug, safe='-()') + '.html')


def model_from_catalog(item):
    code=re.sub('[^A-Z0-9]','',item['ST_CODE'].upper())
    candidates=re.findall(r'(?<![A-Za-z0-9])(?:RM\s*)?[A-Za-z0-9][A-Za-z0-9./_-]{3,}',item['ST_NAME'],re.I)
    if item.get('ST_ITEMGROUP')=='ROLEX' and code[:6].isdigit():
        refs=[x.strip() for x in candidates if re.match(r'^M?'+re.escape(code[:6])+r'(?:[^0-9]|$)',x,re.I)]
        if refs:return max(refs,key=len)
    matches=[x.strip() for x in candidates if re.search(r'\d',x) and code.startswith(re.sub('[^A-Z0-9]','',x.upper()))]
    return max(matches,key=len) if matches else None

def fetch_catalog(progress=lambda value:None):
    products, seen_source, menus = {}, set(), []
    slugs = ['patek-philippe','rolex','richard-mille','audemars-piguet']
    page_count = 0
    def get(client, url, params=None):
        for attempt in range(3):
            time.sleep(2)
            try:
                response=client.get(url,params=params,timeout=(10,35))
                response.raise_for_status()
                return response.text
            except (requests.ConnectionError,requests.Timeout,requests.exceptions.ChunkedEncodingError):
                if attempt==2:raise
                time.sleep((3,8)[attempt])
    with requests.Session() as client:
        client.cookies.set('n_vip_curr','HKD',domain='www.vipstation.com.hk',path='/')
        client.headers['User-Agent']='HourStackPriceMonitor/1.0 (daily public listing quotes)'
        for slug in slugs:
            base='https://www.vipstation.com.hk/tc/watches/'+slug
            first=get(client,base)
            dept=variable(first,'deptList')
            if dept.get('ST_TITLE') not in BRANDS.values():raise ValueError('來源品牌分類不符')
            brand=dept['ST_TITLE']
            options=variable(first,'otherList')
            series=next((x['LT_VALUES'] for x in options if x['ST_CODE']=='st_series'),[])
            prices=next((x['LT_VALUES'] for x in options if x['ST_CODE']=='no_price'),[])
            menus.append(dict(brand=brand,source_url=base,series=series,price_ranges=prices))
            # Each series query is the source's own classification, never inferred from titles.
            for chosen in series or [None]:
                params={'st_series':chosen} if chosen else {}
                html=get(client,base,params) if chosen else first
                info=variable(html,'pageInfo');pages=int(info['totpage'])
                if not 0<=pages<=300:raise ValueError('來源頁數異常')
                local_seen=set()
                for page in range(1,max(pages,1)+1):
                    if page>1:html=get(client,base,dict(params,page=page))
                    info=variable(html,'pageInfo');items=variable(html,'itemList') or []
                    if int(info['totpage'])!=pages or (pages and int(info['currentpage'])!=page):raise ValueError('來源分頁不完整')
                    if pages>1 and not items:raise ValueError('來源分頁資料缺漏')
                    page_count+=1
                    progress(f'{brand}｜{chosen or "全部系列"}｜第 {page}/{max(pages,1)} 頁｜已取得 {len(products)} 筆報價')
                    for item in items:
                        code=item.get('ST_CODE')
                        if not code or code in local_seen:raise ValueError('來源分頁重複')
                        local_seen.add(code);seen_source.add(code)
                        basic=normalize(item)
                        if not basic:continue
                        if BRANDS.get(item.get('ST_ITEMGROUP'))!=brand:raise ValueError('來源混入非選取品牌')
                        model=model_from_catalog(item)
                        if model and chosen:
                            detail=dict(ST_CODE=code,ST_WEB_SUBCATALOG=brand,ST_PRODETAILS=[{'ST_KEY':'型號','ST_VALUE':model},{'ST_KEY':'系列','ST_VALUE':chosen}])
                        else:
                            detail=variable(get(client,basic['url']),'iteminfo')
                        product=normalize(item,detail)
                        # A product appearing under multiple source labels remains one listing.
                        products.setdefault(code,product)
    if not products:raise ValueError('四品牌沒有可核對的公開港幣報價，保留上次資料')
    return list(products.values()),page_count,len(seen_source),{'category':'手錶','menus':menus}


def refresh_if_due(connect, force=False):
    now = datetime.now(TZ)
    with connect() as lock:
        if not lock.execute('SELECT pg_try_advisory_lock(68234017)').fetchone()[0]:
            return False
        try:
            last = lock.execute("SELECT checked_at FROM market_trend_runs WHERE status='completed' ORDER BY checked_at DESC LIMIT 1").fetchone()
            # Bootstrap once; thereafter the existing noon cron is the only daily trigger.
            if not force and last and (now.hour != 12 or last[0].astimezone(TZ) >= now.replace(hour=12,minute=0,second=0,microsecond=0)):
                return False
            with connect() as c:
                c.execute("INSERT INTO market_update_state(singleton,status,started,error) VALUES(true,'running',now(),'') ON CONFLICT(singleton) DO UPDATE SET status='running',started=now(),finished=NULL,error=''")
            def progress(value):
                with connect() as c:c.execute('UPDATE market_update_state SET progress=%s WHERE singleton=true',(value,))
            products, pages, total, metadata = fetch_catalog(progress)
            checked = datetime.now(TZ)
            with connect() as c:
                with c.cursor() as cur:
                    cur.executemany('''INSERT INTO market_trend_products(source_id,variant_key,brand,series,model,title,image_url,url)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(source_id,variant_key) DO UPDATE SET
                        brand=EXCLUDED.brand,series=EXCLUDED.series,model=EXCLUDED.model,title=EXCLUDED.title,image_url=EXCLUDED.image_url,url=EXCLUDED.url''',
                        [tuple(p[k] for k in ('source_id','variant_key','brand','series','model','title','image_url','url')) for p in products])
                    cur.executemany('''INSERT INTO market_trend_prices(source_id,variant_key,observed_date,price,checked_at)
                        VALUES(%s,%s,%s,%s,%s) ON CONFLICT(source_id,variant_key,observed_date) DO UPDATE
                        SET price=EXCLUDED.price,checked_at=EXCLUDED.checked_at''',
                        [(p['source_id'],p['variant_key'],now.date(),p['price'],checked) for p in products])
                c.execute("""INSERT INTO market_trend_runs(observed_date,checked_at,status,count,pages,source_count,error,metadata)
                    VALUES(%s,%s,'completed',%s,%s,%s,'',%s::jsonb) ON CONFLICT(observed_date) DO UPDATE
                    SET checked_at=EXCLUDED.checked_at,status='completed',count=EXCLUDED.count,pages=EXCLUDED.pages,source_count=EXCLUDED.source_count,error='',metadata=EXCLUDED.metadata""",
                    (now.date(),checked,len(products),pages,total,json.dumps(metadata,ensure_ascii=False)))
                c.execute("UPDATE market_update_state SET status='completed',finished=now(),error='' WHERE singleton=true")
            return True
        except Exception:
            with connect() as c:
                c.execute("UPDATE market_update_state SET status='failed',finished=now(),error='來源更新失敗，已保留上次完整資料，請稍後重試' WHERE singleton=true")
            raise
        finally:
            lock.execute('SELECT pg_advisory_unlock(68234017)')


def install(app, connect, protected):
    @app.get('/api/market-trends')
    @protected
    def trends():
        with connect() as c:
            state = c.execute("SELECT status,started,finished,error,progress FROM market_update_state WHERE singleton=true").fetchone()
            locked=c.execute("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory' AND objid=68234017 AND granted)").fetchone()[0]
            running = bool(locked or (state and state[0]=='pending' and state[1] > datetime.now(TZ)-timedelta(minutes=2)))
            update_state = {'running':running,'status':state[0] if state else 'idle','error':state[3] if state else '', 'progress':state[4] if state else ''}
            last = c.execute("SELECT observed_date,checked_at,count,metadata FROM market_trend_runs WHERE status='completed' ORDER BY checked_at DESC LIMIT 1").fetchone()
            if not last:
                return jsonify(items=[], brands=list(BRANDS.values()), updated=None, source=SOURCE, update_state=update_state)
            rows = c.execute('''SELECT p.source_id,p.variant_key,p.brand,p.series,p.model,p.title,p.image_url,p.url,
                h.price,prev.price,(SELECT jsonb_agg(jsonb_build_object('date',d.observed_date,'price',d.price) ORDER BY d.observed_date)
                FROM market_trend_prices d WHERE d.source_id=p.source_id AND d.variant_key=p.variant_key AND d.observed_date >= %s)
                FROM market_trend_products p JOIN market_trend_prices h USING(source_id,variant_key)
                LEFT JOIN market_trend_prices prev ON prev.source_id=h.source_id AND prev.variant_key=h.variant_key
                AND prev.observed_date=h.observed_date-1 WHERE h.observed_date=%s AND h.checked_at=%s ORDER BY p.brand,p.series,p.model,p.source_id''',
                (last[0]-timedelta(days=365),last[0],last[1])).fetchall()
        fields=['source_id','variant_key','brand','series','model','title','image_url','url','price','previous_price','history']
        return jsonify(items=[dict(zip(fields,r)) for r in rows],brands=list(BRANDS.values()),
                       updated=last[1].isoformat(),date=last[0].isoformat(),source=SOURCE,update_state=update_state,source_menu=last[3] if last else {})

    @app.post('/api/market-trends/refresh')
    @protected
    def manual_market_refresh():
        if request.headers.get('X-Watch-Monitor') != '1':
            return jsonify(error='Missing request header'), 403
        with connect() as c:
            if not c.execute('SELECT pg_try_advisory_xact_lock(68234017)').fetchone()[0]:
                return jsonify(error='行情正在更新中'), 409
            row = c.execute("INSERT INTO market_update_state(singleton,status,started,error) VALUES(true,'pending',now(),'') ON CONFLICT(singleton) DO UPDATE SET status='pending',started=now(),finished=NULL,error='' WHERE market_update_state.status<>'pending' OR market_update_state.started < now()-interval '2 minutes' RETURNING singleton").fetchone()
            if not row:
                return jsonify(error='行情正在更新中'), 409
        try:
            subprocess.Popen([sys.executable,os.path.join(app.root_path,'app.py'),'market-force'],cwd=app.root_path)
        except Exception:
            with connect() as c:
                c.execute("UPDATE market_update_state SET status='failed',finished=now(),error='無法啟動行情更新，請重試' WHERE singleton=true")
            return jsonify(error='無法啟動行情更新'), 503
        return jsonify(started=True), 202
