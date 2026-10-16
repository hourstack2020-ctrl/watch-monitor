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
