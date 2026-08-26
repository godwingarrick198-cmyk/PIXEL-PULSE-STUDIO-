import os

def build_bot():
    token=os.getenv('TELEGRAM_BOT_TOKEN')
    if not token: return None
    try:
        from telegram.ext import Application
        return Application.builder().token(token).build()
    except Exception:
        return None
