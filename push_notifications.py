"""Web Push for explicitly subscribed devices; no credentials in payloads."""
import os,json,base64,hashlib,urllib.parse
from pywebpush import webpush,WebPushException

def configured():return bool(os.getenv('VAPID_PRIVATE_KEY') and os.getenv('VAPID_PUBLIC_KEY'))

def subscription_id(endpoint):return hashlib.sha256(endpoint.encode()).hexdigest()

def validate_subscription(value):
    if not isinstance(value,dict):raise ValueError('Invalid subscription')
    endpoint=value.get('endpoint','')
    if not isinstance(endpoint,str) or len(endpoint)>4096:raise ValueError('Invalid endpoint')
    parsed=urllib.parse.urlparse(endpoint);host=parsed.hostname or ''
    if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in (None,443) or parsed.fragment:raise ValueError('Invalid endpoint')
    if not (host.endswith('.push.apple.com') or host=='fcm.googleapis.com' or host=='updates.push.services.mozilla.com'):raise ValueError('Unsupported push provider')
    keys=value.get('keys',{})
    if not isinstance(keys,dict):raise ValueError('Invalid keys')
    for name,length in [('p256dh',65),('auth',16)]:
        raw=keys.get(name,'')
        if not isinstance(raw,str) or len(raw)>200:raise ValueError('Invalid key')
        try:decoded=base64.b64decode(raw+'='*((-len(raw))%4),altchars=b'-_',validate=True)
        except Exception:raise ValueError('Invalid key')
        if len(decoded)!=length or (name=='p256dh' and decoded[0]!=4):raise ValueError('Invalid key')
    return {'endpoint':endpoint,'keys':{name:keys[name] for name in ['p256dh','auth']}}

def send(subscription,payload):
    return webpush(subscription_info=subscription,data=json.dumps(payload,ensure_ascii=False),vapid_private_key=os.environ['VAPID_PRIVATE_KEY'],vapid_claims={'sub':os.getenv('VAPID_SUBJECT','https://hourstack-watch-monitor.onrender.com')},ttl=3600,timeout=15)

def should_notify(previous,price):
    return previous is None or not previous[1] or price<previous[0]

def notification_payload(items):
    if len(items)==1:
        x=items[0];r=x['competitor'];b=x['baseline']
        return {'title':f"低於鐘點站｜{x['brand']} {x['model']}", 'body':f"{r['site']} NT${r['price']:,}｜鐘點站 NT${b['price']:,}\n價差 NT${x['difference']:,}｜{x['year']}年・{x['dial_color']}面・{x['strap']}",'url':'/#comparisonSection','tag':'low-price-'+subscription_id(r['site']+r['url'])[:20]}
    lines=[f"{x['competitor']['site']} {x['model']}｜低 NT${x['difference']:,}" for x in items[:3]]
    return {'title':f'發現 {len(items)} 筆低於鐘點站的商品','body':'\n'.join(lines)+('（另有更多，點擊查看）' if len(items)>3 else ''),'url':'/#comparisonSection','tag':'low-price-summary'}

def notify_low_prices(connect,compare):
    if not configured():return {'sent':0,'failed':0}
    with connect() as c:
        subscriptions=c.execute('SELECT id,subscription FROM push_subscriptions').fetchall()
    if not subscriptions:return {'sent':0,'failed':0}
    with connect() as c:
        fields=['site','url','title','price','status','missing_runs']
        rows=[dict(zip(fields,r)) for r in c.execute('SELECT site,url,title,price,status,missing_runs FROM watches WHERE price>0 AND missing_runs=0').fetchall()]
    matches=compare(rows)['items'];sent=failed=0
    for sid,subscription in subscriptions:
        with connect() as c:
            previous={(r[0],r[1]):(r[2],r[3]) for r in c.execute('SELECT site,url,last_price,active FROM push_alert_state WHERE subscription_id=%s',(sid,)).fetchall()}
        alerts=[x for x in matches if should_notify(previous.get((x['competitor']['site'],x['competitor']['url'])),x['competitor']['price'])]
        if alerts:
            try:send(subscription,notification_payload(alerts));sent+=1
            except WebPushException as exc:
                if exc.response is not None and exc.response.status_code in (404,410):
                    with connect() as c:c.execute('DELETE FROM push_subscriptions WHERE id=%s',(sid,))
                failed+=1;continue
            except Exception:failed+=1;continue
        with connect() as c:
            c.execute('UPDATE push_alert_state SET active=false WHERE subscription_id=%s',(sid,))
            alert_keys={(x['competitor']['site'],x['competitor']['url']) for x in alerts}
            with c.cursor() as cur:
                cur.executemany('''INSERT INTO push_alert_state(subscription_id,site,url,last_price,active) VALUES(%s,%s,%s,%s,true)
                    ON CONFLICT(subscription_id,site,url) DO UPDATE SET last_price=EXCLUDED.last_price,active=true,
                    sent_at=CASE WHEN %s THEN now() ELSE push_alert_state.sent_at END''',[
                    (sid,x['competitor']['site'],x['competitor']['url'],x['competitor']['price'],(x['competitor']['site'],x['competitor']['url']) in alert_keys) for x in matches])
    return {'sent':sent,'failed':failed}


def initialize_event_cursor(c,sid):
    c.execute("""INSERT INTO push_event_cursor(subscription_id,listing_id,history_id)
        SELECT %s,COALESCE((SELECT max(id) FROM listing_events),0),COALESCE((SELECT max(id) FROM history),0)
        ON CONFLICT(subscription_id) DO NOTHING""",(sid,))

def market_payload(listings,changes):
    up=sum(x['price']>x['old_price'] for x in changes)
    down=len(changes)-up
    lines=[f"上架 {len(listings)}（含重新上架）｜漲價 {up}｜降價 {down}"]
    for x in listings[:4]:lines.append(f"{x['site']} {x['model'] or (x['title'] or '')[:40]} {'重新上架' if x['event_type']=='returned' else '新上架'}")
    for x in changes[:4]:lines.append(f"{x['site']} {x['model'] or (x['title'] or '')[:40]} NT${x['old_price']:,} → NT${x['price']:,}")
    site=(listings or changes)[0]['site']
    if len(listings)>4 or len(changes)>4:lines.append('另有更多商品，點擊查看')
    return {'title':site+'｜上架／價格變動通知','body':'\n'.join(lines),'url':'/#inventorySection','tag':'market-events-'+subscription_id(site)[:12]}

def notify_market_events(connect):
    if not configured():return {'sent':0,'failed':0}
    with connect() as c:subscriptions=c.execute('SELECT id,subscription FROM push_subscriptions').fetchall()
    sent=failed=0
    for sid,subscription in subscriptions:
        expired=False
        with connect() as c:
            initialize_event_cursor(c,sid)
            ceiling=c.execute('SELECT COALESCE((SELECT max(id) FROM listing_events),0),COALESCE((SELECT max(id) FROM history),0)').fetchone()
        for site in ['永生','玩錶舍','雷達站']:
            with connect() as c:
                c.execute("""INSERT INTO push_market_cursor(subscription_id,site,listing_id,history_id)
                    SELECT subscription_id,%s,listing_id,history_id FROM push_event_cursor WHERE subscription_id=%s
                    ON CONFLICT(subscription_id,site) DO NOTHING""",(site,sid))
                previous=c.execute('SELECT listing_id,history_id FROM push_market_cursor WHERE subscription_id=%s AND site=%s',(sid,site)).fetchone()
                listings=[dict(zip(['site','url','title','model','price','event_type'],r)) for r in c.execute("""SELECT site,url,title,model,price,event_type FROM listing_events
                    WHERE id>%s AND id<=%s AND site=%s AND event_type IN ('listed','returned') ORDER BY id""",(previous[0],ceiling[0],site)).fetchall()]
                changes=[dict(zip(['site','url','title','model','price','old_price'],r)) for r in c.execute("""WITH prices AS (
                    SELECT id,site,url,price,lag(price) OVER(PARTITION BY site,url ORDER BY checked,id) old_price
                    FROM history WHERE site=%s AND id<=%s)
                    SELECT h.site,h.url,w.title,w.model,h.price,h.old_price FROM prices h
                    LEFT JOIN watches w ON w.site=h.site AND w.url=h.url
                    WHERE h.id>%s AND h.old_price IS NOT NULL AND h.price<>h.old_price ORDER BY h.id""",(site,ceiling[1],previous[1])).fetchall()]
            if listings or changes:
                try:send(subscription,market_payload(listings,changes));sent+=1
                except WebPushException as exc:
                    if exc.response is not None and exc.response.status_code in (404,410):
                        with connect() as c:c.execute('DELETE FROM push_subscriptions WHERE id=%s',(sid,))
                        expired=True
                    failed+=1
                    if expired:break
                    continue
                except Exception:failed+=1;continue
            with connect() as c:c.execute('UPDATE push_market_cursor SET listing_id=GREATEST(listing_id,%s),history_id=GREATEST(history_id,%s) WHERE subscription_id=%s AND site=%s',(ceiling[0],ceiling[1],sid,site))
        if not expired:
            with connect() as c:c.execute("""UPDATE push_event_cursor SET
                listing_id=(SELECT min(listing_id) FROM push_market_cursor WHERE subscription_id=%s),
                history_id=(SELECT min(history_id) FROM push_market_cursor WHERE subscription_id=%s)
                WHERE subscription_id=%s""",(sid,sid,sid))
    return {'sent':sent,'failed':failed}
