from datetime import datetime, timezone, timedelta
import uuid, math
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.models.entities import Campaign, CampaignProspect, Prospect
from app.core.config import get_settings
from app.core.logging import events

class CampaignService:
    def __init__(self): self.s=get_settings()
    def create(self,db,name,target,duration_days=1,industries=None,countries=None,services=None,priority='NORMAL'):
        start=datetime.now(timezone.utc); end=start+timedelta(days=duration_days); daily=math.ceil(target/duration_days)
        daily=min(daily,self.s.MAX_DAILY_PROSPECTS)
        c=Campaign(campaign_id='PPS-'+uuid.uuid4().hex[:10].upper(),name=name,status='DRAFT',priority=priority,target_prospects=target,remaining_prospects=target,start_time=start,end_time=end,daily_limit=daily,industries=industries or [],countries=countries or [],services=services or [],outreach_limit=self.s.MAX_DAILY_OUTREACH)
        db.add(c); db.commit(); db.refresh(c); return c
    def set_status(self,db,campaign_id,status):
        c=db.scalar(select(Campaign).where(Campaign.campaign_id==campaign_id));
        if not c: return None
        c.status=status; db.commit(); return c
    def due_campaigns(self,db):
        return db.scalars(select(Campaign).where(Campaign.status=='RUNNING').order_by(Campaign.priority.desc(),Campaign.created_at)).all()
