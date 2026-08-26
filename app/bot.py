import hashlib
import httpx
from app.core.config import get_settings

settings = get_settings()


def webhook_secret():
    return hashlib.sha256(settings.TELEGRAM_BOT_TOKEN.encode()).hexdigest()


async def telegram_api(method, payload=None):
    if not settings.TELEGRAM_BOT_TOKEN:
        return None
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, json=payload or {})
        response.raise_for_status()
        return response.json()


async def set_webhook():
    if not settings.TELEGRAM_BOT_TOKEN or not settings.BASE_URL:
        return False
    result = await telegram_api("setWebhook", {
        "url": settings.BASE_URL.rstrip("/") + "/api/telegram/webhook",
        "secret_token": webhook_secret(),
        "drop_pending_updates": True,
        "allowed_updates": ["message"],
    })
    return bool(result and result.get("ok"))


async def delete_webhook():
    if not settings.TELEGRAM_BOT_TOKEN:
        return False
    result = await telegram_api("deleteWebhook", {"drop_pending_updates": True})
    return bool(result and result.get("ok"))


async def send_message(chat_id, text):
    return await telegram_api("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    })
