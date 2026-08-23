import re, asyncio
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from sqlalchemy import select, func
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.entities import Campaign, Prospect, Order, OutreachMessage, Payment
from app.services.campaigns import CampaignService

s=get_settings(); cs=CampaignService()
def allowed(update): return bool(s.TELEGRAM_CHAT_ID and str(update.effective_chat.id)==str(s.TELEGRAM_CHAT_ID))
def panel():
    return InlineKeyboardMarkup([[InlineKeyboardButton('HUNT',callback_data='hunt'),InlineKeyboardButton('PAUSE',callback_data='pause')],[InlineKeyboardButton('RESUME',callback_data='resume'),InlineKeyboardButton('STOP',callback_data='stop')],[InlineKeyboardButton('STATUS',callback_data='status'),InlineKeyboardButton('LEADS',callback_data='leads')],[InlineKeyboardButton('ORDERS',callback_data='orders'),InlineKeyboardButton('REVENUE',callback_data='revenue')]])
async def start(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not allowed(update):return
    await update.message.reply_text('PIXEL PULSE STUDIO\n━━━━━━━━━━━━━━━━\n🤖 Agent: READY\n\nUse /hunt 100 or /hunt 500 7d\nUse /status for the full dashboard.',reply_markup=panel())
async def hunt(update,context):
    if not allowed(update):return
    args=context.args; target=int(args[0]) if args and args[0].isdigit() else 100; days=1
    if len(args)>1:
        m=re.match(r'(\d+)([dw])',args[1].lower()); days=int(m.group(1))*(7 if m and m.group(2)=='w' else 1) if m else 1
    db=SessionLocal(); c=cs.create(db,'Telegram Hunt',target,days); db.close(); await update.message.reply_text(f'CAMPAIGN CREATED\n\nCampaign: {c.campaign_id}\nTarget: {target}\nDuration: {days} day(s)\nDaily target: ~{c.daily_limit}\nStatus: READY\n\nUse /resume {c.campaign_id} to start.')
async def status(update,context):
    if not allowed(update):return
    db=SessionLocal(); c=db.scalar(select(Campaign).where(Campaign.status=='RUNNING').order_by(Campaign.created_at.desc())); prospects=db.scalar(select(func.count(Prospect.id))) or 0; out=db.scalar(select(func.count(OutreachMessage.id))) or 0; orders=db.scalar(select(func.count(Order.id)).where(Order.status.in_(['PAID','IN_PRODUCTION','QC','READY']))) or 0; revenue=db.scalar(select(func.sum(Payment.amount)).where(Payment.status=='PAID')) or 0; db.close()
    await update.message.reply_text(f'PIXEL PULSE STUDIO\n━━━━━━━━━━━━━━━━\n🤖 Agent: {"🟢 RUNNING" if c else "⚪ IDLE"}\n🎯 Active Campaign: {c.name if c else "None"}\n📊 Prospects: {prospects}\n📤 Outreach: {out}\n💳 Orders: {orders}\n💰 Revenue: ${revenue:.2f}',reply_markup=panel())
async def campaigns(update,context):
    if not allowed(update):return
    db=SessionLocal(); rows=db.scalars(select(Campaign).order_by(Campaign.created_at.desc()).limit(10)).all();db.close(); await update.message.reply_text('\n'.join(f'{c.campaign_id} — {c.status} — {c.completed_prospects}/{c.target_prospects}' for c in rows) or 'No campaigns.')
async def resume(update,context):
    if not allowed(update):return
    cid=context.args[0] if context.args else None;db=SessionLocal();
    if cid: c=cs.set_status(db,cid,'RUNNING')
    else: c=db.scalar(select(Campaign).where(Campaign.status=='PAUSED').order_by(Campaign.created_at.desc())); c.status='RUNNING' if c else None; db.commit() if c else None
    db.close(); await update.message.reply_text(f'Campaign {c.campaign_id if c else "not found"} is RUNNING.' if c else 'No paused campaign.')
async def pause(update,context):
    if not allowed(update):return
    db=SessionLocal(); c=db.scalar(select(Campaign).where(Campaign.status=='RUNNING').order_by(Campaign.created_at.desc()));
    if c:c.status='PAUSED';db.commit()
    db.close();await update.message.reply_text(f'Paused {c.campaign_id}.' if c else 'No running campaign.')
async def stop(update,context):
    if not allowed(update):return
    db=SessionLocal(); rows=db.scalars(select(Campaign).where(Campaign.status=='RUNNING')).all();
    for c in rows:c.status='STOPPED'
    db.commit();db.close();await update.message.reply_text('Prospecting and outreach stopped. Existing paid orders remain intact.')
async def emergency(update,context):
    if not allowed(update):return
    s.OUTREACH_ENABLED=False
    db=SessionLocal(); rows=db.scalars(select(Campaign).where(Campaign.status=='RUNNING')).all();
    for c in rows:c.status='PAUSED'
    db.commit();db.close();await update.message.reply_text('🚨 EMERGENCY STOP ACTIVE\nProspecting/outreach/follow-ups/new payment requests disabled. Paid orders are untouched.')

async def cancel(update,context):
    if not allowed(update):return
    cid=context.args[0] if context.args else None
    if not cid: return await update.message.reply_text('Usage: /cancel <campaign_id>')
    db=SessionLocal(); c=cs.set_status(db,cid,'CANCELLED'); db.close(); await update.message.reply_text(f'Cancelled {cid}.' if c else 'Campaign not found.')
async def restart(update,context):
    if not allowed(update):return
    cid=context.args[0] if context.args else None
    if not cid: return await update.message.reply_text('Usage: /restart <campaign_id>')
    db=SessionLocal(); c=cs.set_status(db,cid,'RUNNING'); db.close(); await update.message.reply_text(f'Restarted {cid}.' if c else 'Campaign not found.')
async def leads(update,context):
    if not allowed(update):return
    db=SessionLocal(); rows=db.scalars(select(Prospect).where(Prospect.qualification_score>=s.MIN_QUALIFICATION_SCORE).order_by(Prospect.created_at.desc()).limit(10)).all(); db.close()
    await update.message.reply_text('\n'.join(f'{p.id}. {p.company_name} — {p.service_match} — {p.qualification_score}/100' for p in rows) or 'No qualified leads yet.')
async def orders_cmd(update,context):
    if not allowed(update):return
    db=SessionLocal(); rows=db.scalars(select(Order).order_by(Order.created_at.desc()).limit(10)).all(); db.close()
    await update.message.reply_text('\n'.join(f'{o.order_id} — {o.package} — {o.currency} {o.amount:.2f} — {o.status}' for o in rows) or 'No orders yet.')
async def revenue(update,context):
    if not allowed(update):return
    db=SessionLocal(); total=db.scalar(select(func.sum(Payment.amount)).where(Payment.status=='PAID')) or 0; db.close(); await update.message.reply_text(f'Verified revenue: ${total:.2f}')
async def stats(update,context):
    if not allowed(update):return
    db=SessionLocal(); discovered=db.scalar(select(func.count(Prospect.id))) or 0; qualified=db.scalar(select(func.count(Prospect.id)).where(Prospect.status=='QUALIFIED')) or 0; outreach=db.scalar(select(func.count(OutreachMessage.id)).where(OutreachMessage.direction=='outbound')) or 0; replies=db.scalar(select(func.count(OutreachMessage.id)).where(OutreachMessage.direction=='inbound')) or 0; payments=db.scalar(select(func.count(Payment.id)).where(Payment.status=='PAID')) or 0; orders=db.scalar(select(func.count(Order.id))) or 0; completed=db.scalar(select(func.count(Order.id)).where(Order.status=='DELIVERED')) or 0; total=db.scalar(select(func.sum(Payment.amount)).where(Payment.status=='PAID')) or 0; db.close()
    await update.message.reply_text(f'Prospects discovered: {discovered}\nProspects qualified: {qualified}\nOutreach sent: {outreach}\nReplies: {replies}\nPayments: {payments}\nOrders: {orders}\nCompleted orders: {completed}\nRevenue: ${total:.2f}')
async def settings_cmd(update,context):
    if not allowed(update):return
    await update.message.reply_text(f'Currency: {s.SERVICE_CURRENCY}\nStarter: ${s.STARTER_PRICE}\nProfessional: ${s.PROFESSIONAL_PRICE}\nPremium: ${s.PREMIUM_PRICE}\nDaily prospects: {s.MAX_DAILY_PROSPECTS}\nDaily outreach: {s.MAX_DAILY_OUTREACH}\nHourly outreach: {s.MAX_HOURLY_OUTREACH}\nQualification threshold: {s.MIN_QUALIFICATION_SCORE}\nTEST_MODE: {s.TEST_MODE}\nFULL_AUTO: {s.FULL_AUTO}')
async def health_cmd(update,context):
    if not allowed(update):return
    await update.message.reply_text('🟢 API core is configured. Use GET /api/health for the machine-readable health check.')

async def natural(update,context):
    if not allowed(update):return
    text=update.message.text.lower()
    if 'pause' in text: return await pause(update,context)
    if 'resume' in text: return await resume(update,context)
    if 'emergency' in text or 'stop everything' in text: return await emergency(update,context)
    m=re.search(r'(?:find|hunt)\s+(\d+)\s*(?:prospects)?(?:\s+over\s+(\d+)\s*(day|days|week|weeks))?',text)
    if m:
        days=int(m.group(2) or 1)*(7 if 'week' in (m.group(3) or '') else 1); context.args=[m.group(1),f'{days}d']; return await hunt(update,context)
    await update.message.reply_text('I can handle commands like “find 500 startups over 7 days”, “pause everything”, “resume”, or “stop hunting”.')
def build_bot():
    if not s.TELEGRAM_BOT_TOKEN:return None
    app=Application.builder().token(s.TELEGRAM_BOT_TOKEN).build(); app.add_handler(CommandHandler('start',start));app.add_handler(CommandHandler('hunt',hunt));app.add_handler(CommandHandler('status',status));app.add_handler(CommandHandler('campaigns',campaigns));app.add_handler(CommandHandler('resume',resume));app.add_handler(CommandHandler('pause',pause));app.add_handler(CommandHandler('stop',stop));app.add_handler(CommandHandler('emergency_stop',emergency));app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,natural));return app
