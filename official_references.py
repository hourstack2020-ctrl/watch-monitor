"""Exact manufacturer variants, verified against official product pages.

This is a reference check, not authentication of a seller's physical watch.
Unknown or abbreviated variants never receive an inferred approval.
"""
import hashlib,json,logging,re,time
from datetime import datetime,timedelta,timezone
from urllib.parse import urlsplit,urljoin
import requests
from bs4 import BeautifulSoup
import bezel_checks

HOSTS={'www.rolex.com','www.patek.com','www.audemarspiguet.com'}
CATALOG=[]
def add(brand,model,dial,url,bezel,proof,reference=None):
    entry=dict(brand=brand,model=model,dial=dial,url=url,bezel=bezel,proof=proof,reference=reference or model)
    entry['key']=hashlib.sha256(json.dumps(entry,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    CATALOG.append(entry)

def rolex(model,dial,collection,variant,bezel,proof):
    add('Rolex',model,dial,'https://www.rolex.com/en-us/watches/'+collection+'/m'+model.lower()+'-'+variant,bezel,proof)

rolex('126610LN','黑','submariner','0001',{'material':'陶瓷','color':'黑'},['black dial','black ceramic'])
rolex('126613LN','黑','submariner','0002',{'material':'陶瓷','color':'黑'},['black dial','black ceramic'])
rolex('126613LB','藍','submariner','0002',{'material':'陶瓷','color':'藍'},['royal blue dial','blue ceramic'])
rolex('126610LV','黑','submariner','0002',{'material':'陶瓷','color':'綠'},['black dial','green ceramic'])
rolex('124060','黑','submariner','0001',{'material':'陶瓷','color':'黑'},['black dial','black ceramic'])
rolex('226627','黑','yacht-master','0001',{'material':'陶瓷','color':'黑'},['intense black dial','matt black cerachrom'])
rolex('126621','黑','yacht-master','0002',{'material':'玫瑰金'},['intense black dial','bezel','everose gold'])
rolex('126621','巧克力','yacht-master','0001',{'material':'玫瑰金'},['chocolate dial','bezel','everose gold'])
rolex('126622','灰','yacht-master','0001',{'material':'鉑金'},['slate dial','bezel','platinum'])
rolex('268621','黑','yacht-master','0004',{'material':'玫瑰金'},['intense black dial','bezel','everose gold'])
rolex('126710GRNR','黑','gmt-master-ii','0003',{'material':'陶瓷','color':'灰黑'},['black dial','grey and black ceramic'])
rolex('226570','黑','explorer-ii','0002',{'material':'精鋼'},['black dial','fixed','24-hour'])
rolex('336934','黑','sky-dweller','0008',{'style':'坑紋圈'},['bright black dial','fluted'])
rolex('127334','白／蜂巢紋','land-dweller','0001',{'style':'坑紋圈'},['intense white','honeycomb','fluted'])
rolex('127234','白／蜂巢紋','land-dweller','0001',{'style':'坑紋圈'},['intense white','honeycomb','fluted'])
rolex('126500LN','黑／小錶盤黑色／計時圈銀色','cosmograph-daytona','0002',{'material':'陶瓷','color':'黑'},['black dial','steel counter rings','black cerachrom bezel'])
rolex('126000','開心果綠','oyster-perpetual','0011',{'style':'光滑圈'},['pistachio','domed'])
rolex('277200','粉紅','oyster-perpetual','0009',{'style':'光滑圈'},['candy pink','domed'])
rolex('278240','薄荷綠','datejust','0011',{'style':'光滑圈'},['mint green','domed'])
rolex('126334','薄荷綠','datejust','0027',{'style':'坑紋圈'},['mint green','fluted'])
rolex('126334','煙燻綠','datejust','0033',{'style':'坑紋圈'},['green ombré','fluted'])
rolex('126334','黑','datejust','0017',{'style':'坑紋圈'},['bright black','fluted'])
rolex('126233','白','datejust','0047',{'style':'坑紋圈'},['white dial','fluted'])
add('Audemars Piguet','15210CR.OO.A002CR.01','煙燻灰／太陽紋',
    'https://www.audemarspiguet.com/us/en/watch-collection/code-1159/15210CR.OO.A002CR.01',
    {},['grey','sunburst','white and pink gold'])
add('Patek Philippe','4962/200R-010','斑馬紋',
    'https://www.patek.com/en/collection/gondolo/4962-200r-010',
    {},['zebra motif','94','spessartites'])

def find_spec(row,model,dial):
    text=row.get('title') or ''
    if re.search(r'改裝|副廠|後鑲|改鑲|非原廠',text):return None
    if not re.search(r'(?<![A-Z0-9])'+re.escape(model)+r'(?![A-Z0-9./-])',text,re.I):return None
    brand=row.get('brand')
    candidates=[s for s in CATALOG if s['model']==model and s['dial']==dial and s['brand']==brand]
    if len(candidates)!=1:return None
    spec=candidates[0]
    attrs=bezel_checks.text_attributes(text)
    if any(attrs[k]!=spec['bezel'][k] for k in set(attrs)&set(spec['bezel'])):return None
    return spec

def pair_check(baseline,other,model,dial,evidence):
    a=find_spec(baseline,model,dial);b=find_spec(other,model,dial)
    if not a or not b or a['key']!=b['key']:return None
    result=(evidence.get('__official__') or {}).get(a['key']) or {}
    if result.get('status')!='verified' or result.get('source_url')!=a['url']:return None
    return dict(source_url=a['url'],checked_at=result['checked_at'],model=model,dial=dial,
        bezel='／'.join(a['bezel'].values()) or '完整型號官方規格',method='官方網站')

def load_checks(connection):
    return {key:dict(result,checked_at=checked.isoformat()) for key,checked,result in connection.execute(
        "SELECT reference_key,checked_at,result FROM official_reference_checks WHERE checked_at>=now()-interval '7 days' AND result->>'status'='verified'").fetchall()}

def fetch_page(session,url):
    for _ in range(3):
        p=urlsplit(url)
        if p.scheme!='https' or p.hostname not in HOSTS or p.port not in (None,443) or p.username or p.password:raise ValueError('非官方來源')
        with session.get(url,timeout=(5,12),stream=True,allow_redirects=False) as r:
            if r.status_code in (301,302,303,307,308):url=urljoin(url,r.headers.get('Location',''));continue
            r.raise_for_status()
            if 'text/html' not in r.headers.get('Content-Type','').lower():raise ValueError('非官方商品網頁')
            data=bytearray()
            for part in r.iter_content(65536):
                data.extend(part)
                if len(data)>2_000_000:raise ValueError('官方頁面過大')
            return bytes(data)
    raise ValueError('官方頁面重新導向過多')

def verify_page(spec,data):
    soup=BeautifulSoup(data,'html.parser')
    # Navigation/search suggestions or embedded scripts cannot establish a match.
    for node in soup(['script','style','nav','footer']):node.decompose()
    text=re.sub(r'\s+',' ',' '.join(soup.stripped_strings)).casefold()
    headings=' '.join(x.get_text(' ',strip=True) for x in soup.find_all(['h1','h2','h3','title'])).casefold()
    ref=spec['reference'].casefold()
    verified=ref in headings and all(p.casefold() in text for p in spec['proof'])
    return dict(status='verified' if verified else 'pending',source_url=spec['url'],
        page_sha256=hashlib.sha256(data).hexdigest(),reason='' if verified else '官方頁面未完整確認對應規格')

def listing_info(row,listings,model,dial,evidence):
    partners=[x for x in listings if (x.get('site')=='鐘點站')!=(row.get('site')=='鐘點站')]
    checks=[x for other in partners if (x:=pair_check(row,other,model,dial,evidence))]
    if not checks:return {}
    match=checks[0]
    return dict(official_source_url=match['source_url'],official_checked_at=match['checked_at'],
        bezel=bezel_checks.text_label(row) if bezel_checks.text_label(row)!='未辨識' else match['bezel'],bezel_method='官方網站規格')

def refresh(connect,rows,limit=8):
    requested={s['key']:s for row in rows if (s:=find_spec(row,row.get('official_model',''),row.get('official_dial','')))}
    if not requested:return 0
    with connect() as lock:
        if not lock.execute('SELECT pg_try_advisory_lock(68234021)').fetchone()[0]:return 0
        try:
            old={key:(checked,result) for key,checked,result in lock.execute('SELECT reference_key,checked_at,result FROM official_reference_checks').fetchall()}
            count=0;now=datetime.now(timezone.utc)
            with requests.Session() as session:
                session.headers['User-Agent']='HourStackReferenceCheck/1.0'
                for key,spec in requested.items():
                    previous=old.get(key);ttl=timedelta(days=7) if previous and previous[1].get('status')=='verified' else timedelta(hours=6)
                    if previous and previous[0]>now-ttl:continue
                    if count>=limit:break
                    try:result=verify_page(spec,fetch_page(session,spec['url']))
                    except (requests.RequestException,ValueError) as exc:
                        result=dict(status='pending',source_url=spec['url'],reason='官方頁面暫時無法核對')
                        logging.warning('Official reference check deferred for %s: %s',spec['model'],type(exc).__name__)
                    with connect() as c:
                        c.execute('INSERT INTO official_reference_checks(reference_key,checked_at,result) VALUES(%s,now(),%s::jsonb) ON CONFLICT(reference_key) DO UPDATE SET checked_at=EXCLUDED.checked_at,result=EXCLUDED.result',(key,json.dumps(result,ensure_ascii=False)))
                    count+=1;time.sleep(1)
            return count
        finally:lock.execute('SELECT pg_advisory_unlock(68234021)')
