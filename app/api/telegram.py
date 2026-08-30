import asyncio, uuid
from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import select, func
from app.db.session import SessionLocal
from app.models.entities import Campaign, CampaignProspect, Prospect, Order, OutreachMessage, Customer, Payment
from app.services.campaigns import CampaignService
from app.services.presentation import PresentationService
from app.services.prospecting import ProspectingService
from app.services.outreach import OutreachService
from app.services.flutterwave import FlutterwaveService
from app.core.config import get_settings
from app.bot import send_message, webhook_secret

router = APIRouter(prefix='/api/telegram')
settings = get_settings(); campaigns = CampaignService(); presentations = PresentationService(); prospecting = ProspectingService(); outreach = OutreachService(); flw = FlutterwaveService()
# Telegram may retry a slow webhook request. Never allow duplicate hunts to run concurrently.
HUNT_LOCK = asyncio.Lock()

def authorized(chat_id):
    admin = getattr(settings, 'TELEGRAM_ADMIN_CHAT_ID', '')
    return not admin or str(chat_id) == str(admin)

async def notify_channel(text):
    channel_id = getattr(settings, 'TELEGRAM_CHANNEL_ID', '')
    if channel_id:
        try: await send_message(channel_id, text)
        except Exception: pass

@router.post('/webhook')
async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: str | None = Header(default=None)):
    if not settings.TELEGRAM_BOT_TOKEN: raise HTTPException(503, 'Telegram bot is not configured')
    if x_telegram_bot_api_secret_token != webhook_secret(): raise HTTPException(401, 'Invalid Telegram webhook secret')
    update = await request.json(); message = update.get('message') or {}; chat = message.get('chat') or {}; chat_id = chat.get('id'); text = (message.get('text') or '').strip()
    if not chat_id or not text: return {'ok': True}
    if text.startswith('/start'):
        await send_message(chat_id, f'Pixel Pulse Studio is online. Your Telegram chat ID is {chat_id}.\n\nCommands:\n/status\n/campaigns\n/newcampaign NAME|TARGET|DAYS|INDUSTRY|COUNTRY|SERVICE\n/hunt CAMPAIGN_ID\n/outreach CAMPAIGN_ID [PROSPECT_ID]\n/prospects\n/orders\n/neworder PACKAGE|NAME|COMPANY|EMAIL|PROSPECT_ID\n/order ORDER_ID\n/pause CAMPAIGN_ID\n/resume CAMPAIGN_ID\n/stop CAMPAIGN_ID\n/generate ORDER_DATABASE_ID')
        return {'ok': True}
    if not authorized(chat_id):
        await send_message(chat_id, 'This bot is online, but this chat is not authorized for controls. Add your Telegram chat ID to TELEGRAM_ADMIN_CHAT_ID in Render.')
        return {'ok': True}
    db = SessionLocal()
    try:
        parts=text.split(); command=parts[0].split('@')[0].lower(); arg=text[len(parts[0]):].strip()
        if command == '/status':
            running=db.scalar(select(Campaign).where(Campaign.status=='RUNNING').order_by(Campaign.created_at.desc())); prospects=db.scalar(select(func.count(Prospect.id))) or 0; outreach_count=db.scalar(select(func.count(OutreachMessage.id)).where(OutreachMessage.status=='SENT')) or 0; orders=db.scalar(select(func.count(Order.id)).where(Order.status.in_(['PAID','IN_PRODUCTION','QC','READY']))) or 0
            msg=f'Agent: {"RUNNING" if running else "IDLE"}\nProspects: {prospects}\nOutreach sent: {outreach_count}\nActive orders: {orders}'
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
                await send_message(chat_id,f'Campaign created.\nID: {c.campaign_id}\nName: {c.name}\nTarget: {c.target_prospects}\nStatus: {c.status}\n\nStart it with:\n/resume {c.campaign_id}\nThen hunt with:\n/hunt {c.campaign_id}')
        elif command == '/hunt':
            if len(parts)!=2: await send_message(chat_id,'Usage: /hunt PPS-XXXXXXXXXX')
            elif HUNT_LOCK.locked():
                await send_message(chat_id,'⏳ A hunt is already running. Please wait for the current hunt to finish; duplicate Telegram retries are blocked.')
            else:
                async with HUNT_LOCK:
                    c=db.scalar(select(Campaign).where(Campaign.campaign_id==parts[1]))
                    if not c: await send_message(chat_id,'Campaign not found. Use /campaigns to see the exact campaign ID.')
                    elif c.status not in ('RUNNING','DRAFT'): await send_message(chat_id,f'Campaign {c.name} is {c.status}. Resume it before hunting.')
                    elif c.remaining_prospects <= 0: await send_message(chat_id,'This campaign has no remaining prospect capacity.')
                    else:
                        limit=min(c.remaining_prospects,c.daily_limit,settings.MAX_PROSPECTS_PER_RUN,10)
                        query={'industry': c.industries[0] if c.industries else '', 'country': c.countries[0] if c.countries else '', 'service': c.services[0] if c.services else '', 'limit': limit}
                        await send_message(chat_id,f'🔎 Hunting up to {limit} qualified prospects for {c.name}...')
                        found=await prospecting.discover(db,query,limit); linked=0
                        for p in found:
                            if not db.scalar(select(CampaignProspect.id).where(CampaignProspect.campaign_id==c.id,CampaignProspect.prospect_id==p.id)):
                                db.add(CampaignProspect(campaign_id=c.id,prospect_id=p.id,status='QUEUED')); linked+=1
                        c.remaining_prospects=max(0,c.remaining_prospects-linked); c.completed_prospects+=linked; db.commit()
                        report=f'🎯 HUNT COMPLETE\nCampaign: {c.name}\nCampaign ID: {c.campaign_id}\nFound: {len(found)}\nQualified/added: {linked}\nRemaining capacity: {c.remaining_prospects}'
                        await send_message(chat_id,'✅ Hunt complete.\nQualified prospects found: '+str(len(found))+'\nAdded to campaign: '+str(linked)+'\nRemaining campaign capacity: '+str(c.remaining_prospects)); await notify_channel(report)
        elif command == '/outreach':
            if len(parts) not in (2,3): await send_message(chat_id,'Usage: /outreach CAMPAIGN_ID [PROSPECT_ID]\nFirst test sends only one email.')
            else:
                code=parts[1]; c=db.scalar(select(Campaign).where(Campaign.campaign_id==code))
                if not c: await send_message(chat_id,'Campaign not found.')
                else:
                    prospect_id=int(parts[2]) if len(parts)==3 else None
                    if prospect_id is None:
                        cp=db.scalar(select(CampaignProspect).where(CampaignProspect.campaign_id==c.id,CampaignProspect.status=='QUEUED').order_by(CampaignProspect.id.asc()))
                        prospect_id=cp.prospect_id if cp else None
                    if not prospect_id: await send_message(chat_id,'No queued prospect is available for outreach.')
                    else:
                        await send_message(chat_id,f'📧 Sending one test outreach for {c.name}...'); result=await outreach.send_one(db,code,prospect_id)
                        if result.get('status')=='SENT':
                            msg=f'📧 OUTREACH SENT\nCampaign: {c.name}\nCampaign ID: {c.campaign_id}\nCompany: {result.get("company_name")}\nProspect ID: {result.get("prospect_id")}\nMessage ID: {result.get("message_id")}\nStatus: SENT'
                            await send_message(chat_id,msg); await notify_channel(msg)
                        else: await send_message(chat_id,f'Outreach {result.get("status")}: {result.get("reason") or result.get("error")}')
        elif command == '/neworder':
            fields=[x.strip() for x in arg.split('|')]
            if len(fields) not in (4,5):
                await send_message(chat_id,'Usage:\n/neworder PACKAGE|NAME|COMPANY|EMAIL|PROSPECT_ID\nPROSPECT_ID is optional.\nExample:\n/neworder STARTER|Test Customer|Test Company|you@example.com|1')
            else:
                package,name,company,email=fields[:4]; prospect_id=int(fields[4]) if len(fields)==5 and fields[4] else None
                prices={'STARTER':settings.STARTER_PRICE,'PROFESSIONAL':settings.PROFESSIONAL_PRICE,'PREMIUM':settings.PREMIUM_PRICE}
                package=package.upper()
                if package not in prices: raise ValueError('Unsupported package. Use STARTER, PROFESSIONAL, or PREMIUM.')
                if '@' not in email or '.' not in email.split('@')[-1]: raise ValueError('Please provide a valid customer email.')
                customer=Customer(name=name,company_name=company or None,email=email,prospect_id=prospect_id); db.add(customer); db.flush()
                order=Order(order_id='PPS-ORD-'+uuid.uuid4().hex[:12].upper(),customer_id=customer.id,prospect_id=prospect_id,package=package,amount=prices[package],currency=settings.SERVICE_CURRENCY,status='PENDING'); db.add(order); db.flush()
                reference='PPS-'+order.order_id+'-'+uuid.uuid4().hex[:6].upper()
                payment=Payment(payment_id='PAY-'+uuid.uuid4().hex[:10],order_id=order.id,reference=reference,amount=order.amount,currency=order.currency); db.add(payment); db.commit()
                try:
                    result=await flw.create_payment(reference,order.amount,order.currency,email,name,order.order_id)
                    payment.payment_url=result.get('link'); db.commit()
                    await send_message(chat_id,f'🧾 ORDER CREATED\nOrder: {order.order_id}\nPackage: {order.package}\nCustomer: {name}\nCompany: {company}\nAmount: {order.amount:g} {order.currency}\nStatus: {order.status}\nReference: {reference}\n\n💳 Payment link:\n{payment.payment_url or "Not available"}')
                except Exception as e:
                    db.rollback(); await send_message(chat_id,f'Order was created but payment-link creation failed.\nOrder: {order.order_id}\nReason: {e}')
        elif command == '/order':
            if len(parts)!=2: await send_message(chat_id,'Usage: /order ORDER_ID\nExample: /order PPS-ORD-XXXXXXXXXXXX')
            else:
                value=parts[1]; order=db.scalar(select(Order).where(Order.order_id==value))
                if not order and value.isdigit(): order=db.get(Order,int(value))
                if not order: await send_message(chat_id,'Order not found. Use /orders to see existing order IDs.')
                else:
                    payment=db.scalar(select(Payment).where(Payment.order_id==order.id))
                    customer=db.get(Customer,order.customer_id)
                    await send_message(chat_id,f'📦 ORDER\nOrder: {order.order_id}\nCustomer: {customer.name if customer else "Unknown"}\nCompany: {customer.company_name if customer else "Unknown"}\nPackage: {order.package}\nAmount: {order.amount:g} {order.currency}\nStatus: {order.status}\nPayment: {payment.status if payment else "NOT CREATED"}\nPayment link: {payment.payment_url if payment and payment.payment_url else "Not available"}')
        elif command in ('/pause','/resume','/stop'):
            if len(parts)!=2: await send_message(chat_id,f'Usage: {command} PPS-XXXXXXXXXX')
            else:
                new_status={'/pause':'PAUSED','/resume':'RUNNING','/stop':'STOPPED'}[command]; campaign=campaigns.set_status(db,parts[1],new_status); await send_message(chat_id,'Campaign not found. Use /campaigns to see the exact campaign ID.' if not campaign else f'{campaign.name}: {campaign.status}')
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
                        p=presentations.generate(db,o.id); await send_message(chat_id,f'Presentation ready for {o.order_id}.\nSlides: {len((p.strategy_json or {}).get("slides",[]))}\nPPTX: {settings.BASE_URL}/api/orders/{o.id}/presentation/pptx\nPDF: {settings.BASE_URL}/api/orders/{o.id}/presentation/pdf')
                    except ValueError as e: await send_message(chat_id,str(e))
        else: await send_message(chat_id,'Unknown command. Use /start to see commands.')
    except (ValueError,TypeError) as e: await send_message(chat_id,f'Could not process that command: {e}')
    finally: db.close()
    return {'ok': True}
