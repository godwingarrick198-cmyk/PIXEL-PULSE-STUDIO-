import hmac, hashlib, base64
import httpx
from app.core.config import get_settings

class FlutterwaveService:
    def __init__(self): self.s=get_settings()
    def sign_valid(self, raw: bytes, signature: str|None):
        if not self.s.FLW_SECRET_HASH or not signature: return False
        digest=base64.b64encode(hmac.new(self.s.FLW_SECRET_HASH.encode(),raw,hashlib.sha256).digest()).decode()
        return hmac.compare_digest(digest,signature)
    async def create_payment(self, reference, amount, currency, email, name, order_id):
        if self.s.TEST_MODE: return {'link':f'{self.s.BASE_URL or "http://localhost"}/test-payment/{reference}','reference':reference}
        if not self.s.FLW_SECRET_KEY: raise RuntimeError('Flutterwave secret key not configured')
        payload={'tx_ref':reference,'amount':amount,'currency':currency,'redirect_url':f'{self.s.BASE_URL}/payment/callback','customer':{'email':email,'name':name},'meta':{'order_id':order_id}}
        async with httpx.AsyncClient(timeout=25) as c:
            r=await c.post(f'{self.s.FLW_BASE_URL}/payments',json=payload,headers={'Authorization':f'Bearer {self.s.FLW_SECRET_KEY}'}); r.raise_for_status(); data=r.json()
        return {'link':data.get('data',{}).get('link'),'reference':reference,'raw':data}
    async def verify(self, transaction_id, expected_reference, expected_amount, expected_currency):
        if self.s.TEST_MODE: return True, {'status':'successful','tx_ref':expected_reference,'amount':expected_amount,'currency':expected_currency}
        async with httpx.AsyncClient(timeout=20) as c:
            r=await c.get(f'{self.s.FLW_BASE_URL}/transactions/{transaction_id}/verify',headers={'Authorization':f'Bearer {self.s.FLW_SECRET_KEY}'}); r.raise_for_status(); d=r.json().get('data',{})
        ok=(d.get('status')=='successful' and d.get('tx_ref')==expected_reference and float(d.get('amount',0))>=float(expected_amount) and d.get('currency')==expected_currency)
        return ok,d
