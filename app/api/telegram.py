from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import select, func
from app.db.session import SessionLocal
from app.models.entities import Campaign, Prospect, Order, OutreachMessage, Project
from app.services.campaigns import CampaignService
from app.services.presentation import PresentationService
from app.core.config import get_settings
from app.bot import send_message, webhook_secret

router = APIRouter(prefix='/api/telegram')
settings = get_settings(); campaigns = CampaignService(); presentations = PresentationService()

def authorized(chat_id):
    admin = getattr(settings, 'TELEGRAM_ADMIN_CHAT_ID', '')
    return not admin or str(chat_id) == str(admin)

@router.post('/webhook')
async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: str | None = Header(default=None)):
    if not settings.TELEGRAM_BOT_TOKEN: raise HTTPException(503, 'Telegram bot is not configured')
    if x_telegram_bot_api_secret_token != webhook_secret(): raise HTTPException(401, 'Invalid Telegram webhook secret')
    update = await request.json(); message = update.get('message') or {}; chat = message.get('chat') or {}; chat_id = chat.get('id'); text = (message.get('text') or '').strip()
    if not chat_id or not text: return {'ok': True}
    if text.startswith('/start'):
        await send_message(chat_id, f'Pixel Pulse Studio is online. Your Telegram chat ID is {chat_id}.\n\nCommands:\n/status\n/campaigns\n/newcampaign NAME|TARGET|DAYS|INDUSTRY|COUNTRY|SERVICE\n/prospects\n/orders\n/pause CAMPAIGN_ID\n/resume CAMPAIGN_ID\n/stop CAMPAIGN_ID\n/generate ORDER_ID')
        return {'ok': True}
    if not authorized(chat_id):
        await send_message(chat_id, 'This bot is online, but this chat is not authorized for controls. Add your Telegram chat ID to TELEGRAM_ADMIN_CHAT_ID in Render.')
        return {'ok': True}
    db = SessionLocal()
    try:
        parts=text.split(); command=parts[0].split('@')[0].lower(); arg=text[len(parts[0]):].strip()
        if command == '/status':
            running=db.scalar(select(Campaign).where(Campaign.status=='RUNNING').order_by(Campaign.created_at.desc())); prospects=db.scalar(select(func.count(Prospect.id))) or 0; outreach=db.scalar(select(func.count(OutreachMessage.id))) or 0; orders=db.scalar(select(func.count(Order.id)).where(Order.status.in_(['PAID','IN_PRODUCTION','QC','READY']))) or 0
            msg=f'Agent: {"RUNNING" if running else "IDLE"}\nProspects: {prospects}\nOutreach: {outreach}\nActive orders: {orders}'
            if running: msg+=f'\nCampaign: {running.campaign_id} — {running.name}'
            await send_message(chat_id,msg)
        elif command == '/campaigns':
            items=db.scalars(select(Campaign).order_by(Campaign.created_at.desc()).limit(10)).all()
            await send_message(chat_id,'No campaigns found.' if not items else 'Campaigns:\n'+'\n'.join(f'{c.campaign_id} | {c.status} | {c.name} | {c.remaining_prospects} remaining' for c in items))
        elif command == '/newcampaign':
            fields=[x.strip() for x in arg.split('|')]
            if len(fields)!=6:
                await send_message(chat_id,'Usage:\n/newcampaign NAME|TARGET|DAYS|INDUSTRY|COUNTRY|SERVICE\nExample:\n/newcampaign SaaS Nigeria Test|3|1|SaaS|Nigeria|Investor/Sales Deck')
            else:
                name,target,days,industry,country,service=fields
                c=campaigns.create(db,name,max(1,int(target)),max(1,int(days)),[industry],[country],[service],'NORMAL')
                await send_message(chat_id,f'Campaign created.\nID: {c.campaign_id}\nName: {c.name}\nTarget: {c.target_prospects}\nStatus: {c.status}\n\nStart it with:\n/resume {c.campaign_id}')
        elif command in ('/pause','/resume','/stop'):
            if len(parts)!=2: await send_message(chat_id,f'Usage: {command} PPS-XXXXXXXXXX')
            else:
                new_status={'/pause':'PAUSED','/resume':'RUNNING','/stop':'STOPPED'}[command]; campaign=campaigns.set_status(db,parts[1],new_status)
                await send_message(chat_id,'Campaign not found. Use /campaigns to see the exact campaign ID.' if not campaign else f'{campaign.name}: {campaign.status}')
        elif command == '/prospects':
            items=db.scalars(select(Prospect).order_by(Prospect.created_at.desc()).limit(10)).all(); await send_message(chat_id,'No prospects found.' if not items else 'Recent prospects:\n'+'\n'.join(f'{p.id}. {p.company_name} — {p.service_match or "n/a"} — score {p.qualification_score}' for p in items))
        elif command == '/orders':
            items=db.scalars(select(Order).order_by(Order.created_at.desc()).limit(10)).all(); await send_message(chat_id,'No orders found.' if not items else 'Recent orders:\n'+'\n'.join(f'{o.order_id} | {o.package} | {o.amount:g} {o.currency} | {o.status}' for o in items))
        elif command == '/generate':
            if len(parts)!=2: await send_message(chat_id,'Usage: /generate ORDER_DATABASE_ID')
            else:
                o=db.get(Order,int(parts[1]))
                if not o: await send_message(chat_id,'Order not found.')
                elif o.status not in ('PAID','IN_PRODUCTION','QC','READY'): await send_message(chat_id,f'Order {o.order_id} is {o.status}. Payment must be PAID before generation.')
                else:
                    try:
                        p=presentations.generate(db,o.id)
                        await send_message(chat_id,f'Presentation ready for {o.order_id}.\nSlides: {len((p.strategy_json or {}).get("slides",[]))}\nPPTX: {settings.BASE_URL}/api/orders/{o.id}/presentation/pptx\nPDF: {settings.BASE_URL}/api/orders/{o.id}/presentation/pdf')
                    except ValueError as e: await send_message(chat_id,str(e))
        else:
            await send_message(chat_id,'Unknown command. Use /start to see commands.')
    except (ValueError,TypeError) as e:
        await send_message(chat_id,f'Could not process that command: {e}')
    finally: db.close()
    return {'ok': True}
