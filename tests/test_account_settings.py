import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from account_settings import install
from flask import Flask
from werkzeug.security import generate_password_hash

class DB:
    def __init__(self): self.row=['HS',generate_password_hash('test-original-123'),'v1',0,None]
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def execute(self,sql,args=None):
        if sql.startswith('UPDATE admin_account SET username='): self.row[:3]=list(args)
        elif 'failed_attempts=failed_attempts+1' in sql: self.row[3]+=1
        elif 'failed_attempts=0' in sql: self.row[3]=0
        return self
    def fetchone(self): return tuple(self.row)

class AccountTest(unittest.TestCase):
    def setUp(self):
        self.db=DB();self.app=Flask(__name__);self.app.secret_key='test-only-secret'
        self.auth,self.login=install(self.app,lambda:self.db,lambda:'v1')
        self.app.add_url_rule('/api/login','login',self.login,methods=['POST'])
        self.client=self.app.test_client();self.headers={'X-Watch-Monitor':'1'}
    def post(self,url,body): return self.client.post(url,json=body,headers=self.headers)
    def test_account_flow(self):
        self.assertEqual(self.client.get('/api/account').status_code,401)
        self.assertEqual(self.post('/api/login',{'username':None,'password':'test-original-123'}).status_code,401)
        self.assertEqual(self.post('/api/login',{'username':'HS','password':'test-original-123'}).status_code,200)
        old_cookie=self.client.get_cookie('session').value
        data=dict(username='NEW',current_password='wrong',new_password='test-updated-456',confirm_password='test-updated-456')
        self.assertEqual(self.post('/api/account',data).status_code,401)
        self.assertEqual(self.db.row[0],'HS')
        data['current_password']='test-original-123';data['confirm_password']='different'
        self.assertEqual(self.post('/api/account',data).status_code,400)
        data['confirm_password']=data['new_password']
        self.assertEqual(self.client.post('/api/account',json=data).status_code,403)
        self.assertEqual(self.post('/api/account',data).status_code,200)
        self.assertNotEqual(self.db.row[1],data['new_password'])
        stale=self.app.test_client();stale.set_cookie('session',old_cookie)
        self.assertEqual(stale.get('/api/account').status_code,401)
        self.assertEqual(self.post('/api/login',{'username':'HS','password':'test-original-123'}).status_code,401)
        self.assertEqual(self.post('/api/login',{'username':'NEW','password':'test-updated-456'}).status_code,200)
        self.assertEqual(self.post('/api/account',dict(username='OnlyName',current_password='test-updated-456')).status_code,200)
        self.assertEqual(self.post('/api/login',dict(username='OnlyName',password='test-updated-456')).status_code,200)
        data=dict(username='OnlyName',current_password='test-updated-456',new_password='password-only-789',confirm_password='password-only-789')
        self.assertEqual(self.client.post('/api/account',json=data,headers={**self.headers,'Origin':'https://other.example'}).status_code,403)
        self.assertEqual(self.post('/api/account',data).status_code,200)
        self.assertEqual(self.post('/api/login',dict(username='OnlyName',password='password-only-789')).status_code,200)
        from base64 import b64encode
        self.assertEqual(self.app.test_client().get('/api/account',headers={'Authorization':'Basic '+b64encode(b'OnlyName:password-only-789').decode()}).status_code,200)

if __name__=='__main__': unittest.main()
