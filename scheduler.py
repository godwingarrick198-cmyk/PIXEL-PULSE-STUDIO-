from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.core.config import get_settings
from app.core.logging import events
from app.db.session import SessionLocal
from app.services.prospecting import ProspectingService
from app.services.outreach import OutreachService
from app.models.entities import Campaign, CampaignProspect, Prospect
from sqlalchemy import select

s=get_settings(); scheduler=AsyncIOScheduler(timezone='UTC')

async def campaign_tick():
    if not s.SCHEDULER_ENABLED:return
    db=SessionLocal()
    try:
        campaigns=db.scalars(select(Campaign).where(Campaign.status=='RUNNING').order_by(Campaign.priority.desc())).all()
        for c in campaigns:
            if c.remaining_prospects<=0: c.status='COMPLETED'; db.commit(); continue
            query={'industry':(c.industries[0] if c.industries else 'startup'),'country':(c.countries[0] if c.countries else 'Nigeria'),'keywords':c.industries or ['startup','business presentation']}
            n=min(c.daily_limit,s.MAX_PROSPECTS_PER_RUN,c.remaining_prospects)
            found=await ProspectingService().discover(db,query,n)
            for p in found:
                try: db.add(CampaignProspect(campaign_id=c.id,prospect_id=p.id,status='QUALIFIED'))
                except Exception: db.rollback()
            c.completed_prospects+=len(found); c.remaining_prospects=max(0,c.target_prospects-c.completed_prospects)
            db.commit()
            if s.FULL_AUTO or s.TEST_MODE:
                for p in found: OutreachService().send_one(db,p,c)
    except Exception as e: events.event('ERROR',component='campaign_tick',error=str(e))
    finally: db.close()

async def followup_tick():
    db=SessionLocal()
    try: OutreachService().process_followups(db)
    finally: db.close()

scheduler.add_job(campaign_tick,'interval',minutes=s.PROSPECT_INTERVAL_MINUTES,id='prospecting',replace_existing=True)
scheduler.add_job(followup_tick,'interval',minutes=s.FOLLOWUP_INTERVAL_MINUTES,id='followups',replace_existing=True)
