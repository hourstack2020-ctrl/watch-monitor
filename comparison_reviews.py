"""Persistent, exact-pair user decisions for uncertain dial comparisons."""
import hashlib
import json
import logging
import push_notifications as push
from pywebpush import WebPushException
import dial_images
import bezel_checks
import official_references


def review_key(baseline,other,dial,model,evidence):
    def identity(row):
        url=row.get('image_url') or ''
        image=evidence.get(url) or {}
        return [row['site'],row['url'],url,image.get('sha256') or 'unavailable']
    payload=[model,dial,identity(baseline),identity(other)]
    bezels=[bezel_checks.text_attributes(x.get('title')) for x in [baseline,other]]
    if any(bezels):payload.append(bezels)
    return hashlib.sha256(json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def listing_pair_id(baseline,other):
    payload=[baseline['site'],baseline['url'],other['site'],other['url']]
    return 'listing:'+hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest()


def load_decisions(connection):
    decisions={}
    for key,choice,details in connection.execute('SELECT pair_key,decision,details FROM comparison_reviews ORDER BY decided_at NULLS FIRST,created_at').fetchall():
        decisions[key]=choice
        if choice in ('approved','rejected'):
            decisions[listing_pair_id(details['baseline'],details['other'])]=key
    return decisions


def pair_state(baseline,other,dial,model,evidence,decisions):
    key=review_key(baseline,other,dial,model,evidence)
    previous=decisions.get(key)
    if previous=='rejected':return key,previous,''
    bezel=bezel_checks.match(baseline,other,evidence)
    b=dial_images.assessment(baseline,dial,evidence)
    o=dial_images.assessment(other,dial,evidence)
    # Either independent channel may establish a match. Missing/conflicting
    # photo evidence must not veto matching listing text, and missing dial
    # wording must not veto matching analysed product photos.
    left_text=baseline.get('_comparison_dial_text',dial)
    right_text=other.get('_comparison_dial_text',dial)
    text_match=bool(left_text and right_text and left_text==right_text and left_text!='未註明')
    photo_match=b['status']=='verified' and o['status']=='verified' and b['bucket']==o['bucket']
    if bezel['matched'] and text_match:return key,'automatic','面盤文字相同；錶圈已核對'
    if bezel['matched'] and photo_match:return key,'automatic','面盤圖片相符；錶圈已核對'
    if not any(x['status']=='conflict' for x in (b,o)):
        official=official_references.pair_check(baseline,other,model,dial,evidence)
        if official:return key,'automatic','官方網站完整規格已核對'
    if not bezel['matched']:return key,'pending','錶圈文字或圖片尚未確認相符'
    if any(row.get('image_url') and row['image_url'] not in evidence for row in [baseline,other]):
        return key,'analysing','圖片核對中'
    reasons=list(dict.fromkeys(x['reason'] for x in [b,o] if x['status']!='verified'))
    return key,'pending','；'.join(reasons) or '面盤文字與圖片皆尚未確認相符'


def review_details(key,baseline,other,dial,model,reason):
    def safe(row):
        return {name:row.get(name) for name in ('site','url','title','brand','model','year','condition','price','image_url')}
    return {'pair_key':key,'baseline':safe(baseline),'other':safe(other),'dial_color':dial,'model':model,'reason':reason}


def save_decision(connection,details,decision):
    connection.execute('''INSERT INTO comparison_reviews(pair_key,decision,details,reason,last_seen,decided_at)
        VALUES(%s,%s,%s::jsonb,%s,now(),now()) ON CONFLICT(pair_key) DO UPDATE SET
        decision=EXCLUDED.decision,details=EXCLUDED.details,reason=EXCLUDED.reason,last_seen=now(),decided_at=now()''',
        (details['pair_key'],decision,json.dumps(details,ensure_ascii=False),details['reason']))


def sync_pending(connect,pairs):
    with connect() as c:
        # Retire stale pending prompts without touching any user decisions.
        c.execute("UPDATE comparison_reviews SET last_seen=now()-interval '2 hours' WHERE decision='pending' AND last_seen>now()-interval '1 hour' AND NOT(pair_key=ANY(%s::text[]))",([d['pair_key'] for d in pairs],))
        for details in pairs:
            c.execute('''INSERT INTO comparison_reviews(pair_key,decision,details,reason,last_seen)
                VALUES(%s,'pending',%s::jsonb,%s,now()) ON CONFLICT(pair_key) DO UPDATE SET
                details=EXCLUDED.details,reason=EXCLUDED.reason,last_seen=now() WHERE comparison_reviews.decision='pending' ''',
                (details['pair_key'],json.dumps(details,ensure_ascii=False),details['reason']))


def notify_pending(connect):
    if not push.configured():return {'sent':0,'failed':0}
    sent=failed=0
    with connect() as lock:
        if not lock.execute('SELECT pg_try_advisory_lock(68234019)').fetchone()[0]:return {'sent':0,'failed':0}
        try:
            with connect() as c:subscriptions=c.execute('SELECT id,subscription FROM push_subscriptions').fetchall()
            for sid,subscription in subscriptions:
                with connect() as c:
                    pairs=c.execute('''SELECT r.pair_key,r.details FROM comparison_reviews r
                        WHERE r.decision='pending' AND r.last_seen>now()-interval '1 hour'
                        AND NOT EXISTS(SELECT 1 FROM comparison_review_notifications n WHERE n.subscription_id=%s AND n.pair_key=r.pair_key)
                        ORDER BY r.created_at,r.pair_key''',(sid,)).fetchall()
                if not pairs:continue
                lines=[f"{d['baseline']['site']} ↔ {d['other']['site']}｜{d['model']}" for key,d in pairs[:3]]
                payload={'title':f'有 {len(pairs)} 組比價需要你確認','body':'\n'.join(lines)+'\n點開選擇「需要比價」或「不需要」','url':'/#comparisonReview','tag':'comparison-review'}
                try:push.send(subscription,payload)
                except WebPushException as exc:
                    if exc.response is not None and exc.response.status_code in (404,410):
                        with connect() as c:c.execute('DELETE FROM push_subscriptions WHERE id=%s',(sid,))
                    failed+=1;continue
                except Exception:
                    logging.warning('Comparison review push failed; will retry later');failed+=1;continue
                with connect() as c:
                    for key,details in pairs:
                        c.execute('INSERT INTO comparison_review_notifications(subscription_id,pair_key) VALUES(%s,%s) ON CONFLICT DO NOTHING',(sid,key))
                sent+=1
            return {'sent':sent,'failed':failed}
        finally:lock.execute('SELECT pg_advisory_unlock(68234019)')


