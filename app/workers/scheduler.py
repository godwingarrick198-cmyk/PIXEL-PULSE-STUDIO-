from datetime import datetime, timezone
from sqlalchemy import select, func
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.entities import Campaign, CampaignProspect, Prospect, OutreachMessage
from app.services.prospecting import ProspectingService
from app.services.outreach import OutreachService

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
except Exception:
    AsyncIOScheduler = None

settings = get_settings()

async def run_campaign_cycle():
    """Run one bounded cycle for every active campaign.

    Campaign duration is controlled by start_time/end_time. The cycle respects
    each campaign's daily prospect/outreach limits and skips suppressed or
    missing-email prospects through the normal services.
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        campaigns = db.scalars(
            select(Campaign).where(
                Campaign.status == 'RUNNING',
                Campaign.start_time <= now,
                Campaign.end_time >= now,
                Campaign.remaining_prospects > 0,
            )
        ).all()
        prospecting = ProspectingService()
        outreach = OutreachService()
        for campaign in campaigns:
            # Hunt only enough to fill the campaign's remaining daily capacity.
            discovered_today = db.scalar(select(func.count(Prospect.id)).join(
                CampaignProspect, CampaignProspect.prospect_id == Prospect.id
            ).where(
                CampaignProspect.campaign_id == campaign.id,
                Prospect.created_at >= now.replace(hour=0, minute=0, second=0, microsecond=0),
            )) or 0
            hunt_limit = max(0, min(campaign.daily_limit - discovered_today, campaign.remaining_prospects, settings.MAX_PROSPECTS_PER_RUN))
            if hunt_limit:
                query = {
                    'industry': campaign.industries[0] if campaign.industries else '',
                    'country': campaign.countries[0] if campaign.countries else '',
                    'service': campaign.services[0] if campaign.services else '',
                    'limit': hunt_limit,
                }
                found = await prospecting.discover(db, query, hunt_limit)
                linked = 0
                for p in found:
                    exists = db.scalar(select(CampaignProspect.id).where(
                        CampaignProspect.campaign_id == campaign.id,
                        CampaignProspect.prospect_id == p.id,
                    ))
                    if not exists:
                        db.add(CampaignProspect(campaign_id=campaign.id, prospect_id=p.id, status='QUEUED'))
                        linked += 1
                campaign.remaining_prospects = max(0, campaign.remaining_prospects - linked)
                campaign.completed_prospects += linked
                db.commit()

            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            sent_today = db.scalar(select(func.count(OutreachMessage.id)).where(
                OutreachMessage.campaign_id == campaign.id,
                OutreachMessage.status == 'SENT',
                OutreachMessage.sent_at >= day_start,
            )) or 0
            send_limit = max(0, min(10, campaign.outreach_limit - sent_today))
            if not send_limit:
                continue
            queued = db.scalars(select(CampaignProspect).where(
                CampaignProspect.campaign_id == campaign.id,
                CampaignProspect.status == 'QUEUED',
            ).order_by(CampaignProspect.id.asc()).limit(send_limit)).all()
            for cp in queued:
                result = await outreach.send_one(db, campaign.campaign_id, cp.prospect_id)
                if result.get('status') not in ('SENT', 'SKIPPED'):
                    break
    finally:
        db.close()

if AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_campaign_cycle, 'interval', minutes=15, id='campaign_cycle', replace_existing=True, max_instances=1, coalesce=True)
else:
    class _NoopScheduler:
        def start(self): pass
        def shutdown(self, wait=False): pass
    scheduler = _NoopScheduler()
