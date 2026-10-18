"""Daily, per-listing public HKD quotes from VIP Station's pre-owned catalogue."""
import hashlib
import json
import logging
import re
import time
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote
import requests
from flask import jsonify, request

SOURCE = 'https://www.vipstation.com.hk/tc/pre-owned-watches'
BRANDS = {'PP':'Patek Philippe','ROLEX':'Rolex','RICHARD MILLE':'Richard Mille','AP':'Audemars Piguet'}
TZ = ZoneInfo('Asia/Taipei')


def variable(html, name):
    match = re.search(r'\bvar\s+' + re.escape(name) + r'\s*=\s*', html)
    if not match:
        raise ValueError('來源資料格式變更：' + name)
    return json.JSONDecoder().raw_decode(html[match.end():])[0]


def normalize(item):
    brand = BRANDS.get(item.get('ST_ITEMGROUP'))
    title = item.get('ST_NAME', '')
    price = item.get('NO_PRICE')
    if not brand or item.get('NO_ISSTOCK') != 1 or item.get('ST_PRICETIPS'):
        return None
    if not isinstance(price, (float, int)) or isinstance(price, bool) or price <= 0:
        return None
    if item.get('ST_CURR') not in ('', None, 'HKD'):
        raise ValueError('來源幣值不是 HKD，保留上次資料')
    model_match = re.search(r'(?:自動|手動|石英)機芯\s+(.+?)\s+(?:\d{1,3}\s*%|全新|未使用|二手)', title, re.I)
    if not model_match:
        return None
    model = model_match.group(1).strip().upper()
    upper = title.upper()
    series = next((s for token, s in [
        ('NAUTILUS','Nautilus'),('AQUANAUT','Aquanaut'),('GRAND COMPLICATIONS','Grand Complications'),
        ('ANNIVERSARY SERIES','Anniversary Series'),('CALATRAVA','Calatrava'),('GONDOLO','Gondolo'),
        ('ROYAL OAK OFFSHORE','Royal Oak Offshore'),('ROYAL OAK CONCEPT','Royal Oak Concept'),
        ('ROYAL OAK','Royal Oak'),('CODE 11.59','Code 11.59'),('CANAPE','Canape'),
        ('DAYTONA','Daytona'),('SKY-DWELLER','Sky-Dweller'),('DAY-DATE','Day-Date'),
        ('DATEJUST','Datejust'),('SUBMARINER','Submariner'),('GMT-MASTER','GMT-Master'),
        ('SEA-DWELLER','Sea-Dweller'),('YACHT MASTER','Yacht-Master'),('EXPLORER','Explorer'),
        ('LADIES','Ladies'),('男仕系列','Men')]
        if token in upper), '系列未標示')
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


def fetch_catalog():
    output, codes = [], set()
    with requests.Session() as client:
        client.cookies.set('n_vip_curr', 'HKD', domain='www.vipstation.com.hk', path='/')
        client.headers['User-Agent'] = 'HourStackPriceMonitor/1.0 (daily public listing quotes)'
        pages = 1
        for page in range(1, 101):
            url = SOURCE if page == 1 else SOURCE + '?page=' + str(page)
            for attempt in range(3):
                try:
                    response = client.get(url, timeout=(10, 35))
                    response.raise_for_status()
                    html = response.text
                    info, items = variable(html, 'pageInfo'), variable(html, 'itemList')
                    break
                except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError):
                    if attempt == 2:
                        raise
                    time.sleep((3, 8)[attempt])
            if page == 1:
                pages = int(info['totpage'])
                if not 1 <= pages <= 100:
                    raise ValueError('來源頁數異常')
            if int(info['currentpage']) != page or int(info['totpage']) != pages or not items:
                raise ValueError('來源分頁不完整，保留上次資料')
            for item in items:
                code = item.get('ST_CODE')
                if code in codes:
                    raise ValueError('來源分頁重複，保留上次資料')
                codes.add(code)
                product = normalize(item)
                if product:
                    output.append(product)
            if page == pages:
                break
            time.sleep(2)
    if not output:
        raise ValueError('來源沒有可核對的公開港幣報價，保留上次資料')
    return output, pages, len(codes)


def refresh_if_due(connect):
    now = datetime.now(TZ)
    with connect() as lock:
        if not lock.execute('SELECT pg_try_advisory_lock(68234017)').fetchone()[0]:
            return False
        try:
            last = lock.execute("SELECT checked_at FROM market_trend_runs WHERE status='completed' ORDER BY checked_at DESC LIMIT 1").fetchone()
            # Bootstrap once; thereafter the existing noon cron is the only daily trigger.
            if last and (now.hour != 12 or last[0].astimezone(TZ) >= now.replace(hour=12,minute=0,second=0,microsecond=0)):
                return False
            products, pages, total = fetch_catalog()
            checked = datetime.now(TZ)
            with connect() as c:
                for p in products:
                    c.execute('''INSERT INTO market_trend_products(source_id,variant_key,brand,series,model,title,image_url,url)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(source_id,variant_key) DO UPDATE SET
                        title=EXCLUDED.title,image_url=EXCLUDED.image_url,url=EXCLUDED.url''',
                        tuple(p[k] for k in ('source_id','variant_key','brand','series','model','title','image_url','url')))
                    c.execute('''INSERT INTO market_trend_prices(source_id,variant_key,observed_date,price,checked_at)
                        VALUES(%s,%s,%s,%s,%s) ON CONFLICT(source_id,variant_key,observed_date) DO UPDATE
                        SET price=EXCLUDED.price,checked_at=EXCLUDED.checked_at''',
                        (p['source_id'],p['variant_key'],now.date(),p['price'],checked))
                c.execute("""INSERT INTO market_trend_runs(observed_date,checked_at,status,count,pages,source_count,error)
                    VALUES(%s,%s,'completed',%s,%s,%s,'') ON CONFLICT(observed_date) DO UPDATE
                    SET checked_at=EXCLUDED.checked_at,status='completed',count=EXCLUDED.count,pages=EXCLUDED.pages,source_count=EXCLUDED.source_count,error=''""",
                    (now.date(),checked,len(products),pages,total))
            return True
        finally:
            lock.execute('SELECT pg_advisory_unlock(68234017)')


def install(app, connect, protected):
    @app.get('/api/market-trends')
    @protected
    def trends():
        with connect() as c:
            last = c.execute("SELECT observed_date,checked_at,count FROM market_trend_runs WHERE status='completed' ORDER BY checked_at DESC LIMIT 1").fetchone()
            if not last:
                return jsonify(items=[], brands=list(BRANDS.values()), updated=None, source=SOURCE)
            rows = c.execute('''SELECT p.source_id,p.variant_key,p.brand,p.series,p.model,p.title,p.image_url,p.url,
                h.price,prev.price,(SELECT jsonb_agg(jsonb_build_object('date',d.observed_date,'price',d.price) ORDER BY d.observed_date)
                FROM market_trend_prices d WHERE d.source_id=p.source_id AND d.variant_key=p.variant_key AND d.observed_date >= %s)
                FROM market_trend_products p JOIN market_trend_prices h USING(source_id,variant_key)
                LEFT JOIN market_trend_prices prev ON prev.source_id=h.source_id AND prev.variant_key=h.variant_key
                AND prev.observed_date=h.observed_date-1 WHERE h.observed_date=%s AND h.checked_at=%s ORDER BY p.brand,p.series,p.model,p.source_id''',
                (last[0]-timedelta(days=365),last[0],last[1])).fetchall()
        fields=['source_id','variant_key','brand','series','model','title','image_url','url','price','previous_price','history']
        return jsonify(items=[dict(zip(fields,r)) for r in rows],brands=list(BRANDS.values()),
                       updated=last[1].isoformat(),date=last[0].isoformat(),source=SOURCE)
