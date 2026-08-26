from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import select, func
from app.db.session import SessionLocal
from app.models.entities import Campaign, Prospect, Order, OutreachMessage
from app.services.campaigns import CampaignService
from app.core.config import get_settings
from app.bot import send_message, webhook_secret

router = APIRouter(prefix='/api/telegram')
settings = get_settings()
campaigns = CampaignService()


def authorized(chat_id):
    admin = getattr(settings, 'TELEGRAM_ADMIN_CHAT_ID', '')
    return not admin or str(chat_id) == str(admin)


@router.post('/webhook')
async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: str | None = Header(default=None)):
    if not settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(503, 'Telegram bot is not configured')
    if x_telegram_bot_api_secret_token != webhook_secret():
        raise HTTPException(401, 'Invalid Telegram webhook secret')

    update = await request.json()
    message = update.get('message') or {}
    chat = message.get('chat') or {}
    chat_id = chat.get('id')
    text = (message.get('text') or '').strip()
    if not chat_id or not text:
        return {'ok': True}

    if text.startswith('/start'):
        await send_message(chat_id, f'Pixel Pulse Studio is online. Your Telegram chat ID is {chat_id}.\n\nCommands: /status /campaigns /prospects /orders /pause CAMPAIGN_ID /resume CAMPAIGN_ID /stop CAMPAIGN_ID')
        return {'ok': True}

    if not authorized(chat_id):
        await send_message(chat_id, 'This bot is online, but this chat is not authorized for controls. Add your Telegram chat ID to TELEGRAM_ADMIN_CHAT_ID in Render.')
        return {'ok': True}

    db = SessionLocal()
    try:
        parts = text.split()
        command = parts[0].split('@')[0].lower()

        if command == '/status':
            running = db.scalar(select(Campaign).where(Campaign.status == 'RUNNING').order_by(Campaign.created_at.desc()))
            prospects = db.scalar(select(func.count(Prospect.id))) or 0
            outreach = db.scalar(select(func.count(OutreachMessage.id))) or 0
            orders = db.scalar(select(func.count(Order.id)).where(Order.status.in_(['PAID','IN_PRODUCTION','QC','READY']))) or 0
            msg = f'Agent: {"RUNNING" if running else "IDLE"}\nProspects: {prospects}\nOutreach: {outreach}\nActive orders: {orders}'
            if running:
                msg += f'\nCampaign: {running.campaign_id} — {running.name}'
            await send_message(chat_id, msg)

        elif command == '/campaigns':
            items = db.scalars(select(Campaign).order_by(Campaign.created_at.desc()).limit(10)).all()
            if not items:
                await send_message(chat_id, 'No campaigns found.')
            else:
                lines = [f'{c.campaign_id} | {c.status} | {c.name} | {c.remaining_prospects} remaining' for c in items]
                await send_message(chat_id, 'Campaigns:\n' + '\n'.join(lines))

        elif command in ('/pause', '/resume', '/stop'):
            if len(parts) != 2:
                await send_message(chat_id, f'Usage: {command} PPS-XXXXXXXXXX')
            else:
                new_status = {'/pause': 'PAUSED', '/resume': 'RUNNING', '/stop': 'STOPPED'}[command]
                campaign = campaigns.set_status(db, parts[1], new_status)
                if not campaign:
                    await send_message(chat_id, 'Campaign not found. Use /campaigns to see the exact campaign ID.')
                else:
                    await send_message(chat_id, f'{campaign.name}: {campaign.status}')

        elif command == '/prospects':
            items = db.scalars(select(Prospect).order_by(Prospect.created_at.desc()).limit(10)).all()
            if not items:
                await send_message(chat_id, 'No prospects found.')
            else:
                lines = [f'{p.id}. {p.company_name} — {p.service_match or "n/a"} — score {p.qualification_score}' for p in items]
                await send_message(chat_id, 'Recent prospects:\n' + '\n'.join(lines))

        elif command == '/orders':
            items = db.scalars(select(Order).order_by(Order.created_at.desc()).limit(10)).all()
            if not items:
                await send_message(chat_id, 'No orders found.')
            else:
                lines = [f'{o.order_id} | {o.package} | {o.amount:g} {o.currency} | {o.status}' for o in items]
                await send_message(chat_id, 'Recent orders:\n' + '\n'.join(lines))

        else:
            await send_message(chat_id, 'Unknown command. Use /status, /campaigns, /prospects, /orders, /pause ID, /resume ID, or /stop ID.')
    finally:
        db.close()

    return {'ok': True}
