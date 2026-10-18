"""Single administrator credentials, persisted as password hashes only."""
import hmac
import os
import re
import secrets
from datetime import datetime, timezone
from flask import request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash


def install(app, connect, initial_version):
    def account(c):
        row = c.execute('SELECT username,password_hash,auth_version,failed_attempts,locked_until FROM admin_account WHERE singleton=true').fetchone()
        if row is None:
            password = os.getenv('ADMIN_PASSWORD', '')
            if not password:
                return None
            c.execute('INSERT INTO admin_account(singleton,username,password_hash,auth_version) VALUES(true,%s,%s,%s) ON CONFLICT(singleton) DO NOTHING',
                      ('HS', generate_password_hash(password), initial_version()))
            row = c.execute('SELECT username,password_hash,auth_version,failed_attempts,locked_until FROM admin_account WHERE singleton=true').fetchone()
        return row

    def current():
        with connect() as c:
            return account(c)

    def password_matches(row, password):
        return isinstance(password, str) and len(password) <= 256 and check_password_hash(row[1], password)

    def authenticated():
        row = current()
        if not row:
            return False
        credentials = request.authorization
        if credentials and credentials.type.lower() == 'basic':
            with connect() as c:
                row = c.execute('SELECT username,password_hash,auth_version,failed_attempts,locked_until FROM admin_account WHERE singleton=true FOR UPDATE').fetchone()
                valid, _ = verify(c, row, credentials.password, credentials.username or '')
            return valid
        return bool(app.secret_key and session.get('user') == row[0] and
                    hmac.compare_digest(session.get('auth_version', ''), row[2]))

    def safe_post():
        return (request.headers.get('X-Watch-Monitor') == '1' and
                (not request.headers.get('Origin') or request.headers['Origin'] == request.host_url.rstrip('/')))

    def verify(c, row, password, username=None):
        if row[4] and row[4] > datetime.now(timezone.utc):
            return False, 429
        valid = password_matches(row, password)
        if username is not None:
            valid = valid and isinstance(username, str) and hmac.compare_digest(username.encode(), row[0].encode())
        if not valid:
            c.execute("UPDATE admin_account SET failed_attempts=failed_attempts+1,locked_until=CASE WHEN failed_attempts>=9 THEN now()+interval '5 minutes' ELSE locked_until END WHERE singleton=true")
            return False, 401
        c.execute('UPDATE admin_account SET failed_attempts=0,locked_until=NULL WHERE singleton=true')
        return True, 200

    def login():
        if not safe_post():
            return jsonify(error='請重新整理後再試'), 403
        if not app.secret_key:
            return jsonify(error='登入服務尚未就緒'), 503
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify(error='帳號或密碼不正確'), 401
        if not isinstance(body.get('username'), str) or not isinstance(body.get('password'), str) or len(body['username']) > 100:
            return jsonify(error='帳號或密碼不正確'), 401
        with connect() as c:
            account(c)
            row = c.execute('SELECT username,password_hash,auth_version,failed_attempts,locked_until FROM admin_account WHERE singleton=true FOR UPDATE').fetchone()
            if not row:
                return jsonify(error='登入服務尚未就緒'), 503
            valid, code = verify(c, row, body.get('password'), body.get('username', ''))
        if not valid:
            return jsonify(error='嘗試次數過多，請 5 分鐘後再試' if code == 429 else '帳號或密碼不正確'), code
        session.clear()
        session.permanent = True
        session.update(user=row[0], auth_version=row[2])
        return jsonify(ok=True)

    @app.get('/api/account')
    def account_info():
        if not authenticated():
            return jsonify(error='請重新登入'), 401
        return jsonify(username=current()[0])

    @app.post('/api/account')
    def change_account():
        if not safe_post():
            return jsonify(error='請重新整理後再試'), 403
        if not authenticated():
            return jsonify(error='請重新登入'), 401
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify(error='資料格式不正確'), 400
        username, password = body.get('username'), body.get('new_password', '')
        if not isinstance(username, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{2,50}', username):
            return jsonify(error='帳號需為 2～50 個英文字母、數字或 _ . -'), 400
        if not isinstance(password, str) or (password and not 8 <= len(password) <= 256):
            return jsonify(error='新密碼需為 8～256 個字元'), 400
        if password != body.get('confirm_password', ''):
            return jsonify(error='兩次新密碼不一致'), 400
        with connect() as c:
            row = c.execute('SELECT username,password_hash,auth_version,failed_attempts,locked_until FROM admin_account WHERE singleton=true FOR UPDATE').fetchone()
            # Recheck the session under the row lock to reject concurrent stale edits.
            if not row or not (session.get('user') == row[0] and hmac.compare_digest(session.get('auth_version', ''), row[2])):
                return jsonify(error='請先使用帳號密碼登入頁面，再修改設定'), 401
            valid, code = verify(c, row, body.get('current_password'))
            if valid:
                if username == row[0] and not password:
                    return jsonify(error='請修改帳號或輸入新密碼'), 400
                c.execute('UPDATE admin_account SET username=%s,password_hash=%s,auth_version=%s,updated_at=now() WHERE singleton=true',
                          (username, generate_password_hash(password) if password else row[1], secrets.token_hex(32)))
        if not valid:
            return jsonify(error='嘗試次數過多，請 5 分鐘後再試' if code == 429 else '目前密碼不正確'), code
        session.clear()
        return jsonify(ok=True, message='已更新，請使用新帳號密碼重新登入')

    return authenticated, login
