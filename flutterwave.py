import hmac, hashlib, base64, httpx
from app.core.config import get_settings

class FlutterwaveService:
    def __init__(self): self.s=get_settings()
    def sign_valid(self, raw, signature):
        if not self.s.FLW_SECRET_HASH or not signature: return False
        digest=base64.b64encode(hmac.new(self.s.FLW_SECRET_HASH.encode(),raw,hashlib.sha256).digest()).decode()
        return hmac.compare_digest(digest,signature)
