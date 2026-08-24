from app.core.config import get_settings
from app.core.logging import events
import httpx
class TelegramNotifier:
    def __init__(self): self.s=get_settings()
    async def send(self,text):
        if not self.s.TELEGRAM_BOT_TOKEN or not self.s.TELEGRAM_CHAT_ID: return
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                await c.post(f'https://api.telegram.org/bot{self.s.TELEGRAM_BOT_TOKEN}/sendMessage',json={'chat_id':self.s.TELEGRAM_CHAT_ID,'text':text})
        except Exception as e: events.event('ERROR',component='telegram_notify',error=str(e))
