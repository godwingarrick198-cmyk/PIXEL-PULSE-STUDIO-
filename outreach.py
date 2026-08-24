from datetime import datetime, timezone, timedelta
import uuid
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.models.entities import Prospect, Campaign, CampaignProspect, OutreachMessage, Followup, SuppressionList
from app.services.email import EmailService
from app.services.ai import AIService
from app.core.config import get_settings
from app.core.logging import events

class OutreachService:
    def __init__(self): self.s=get_settings(); self.email=EmailService(); self.ai=AIService()
    def _counts(self,db):
        now=datetime.now(timezone.utc); day=now.replace(hour=0,minute=0,second=0,microsecond=0); hour=now.replace(minute=0,second=0,microsecond=0)
        daily=db.scalar(select(func.count(OutreachMessage.id)).where(OutreachMessage.direction=='outbound',OutreachMessage.created_at>=day)) or 0
        hourly=db.scalar(select(func.count(OutreachMessage.id)).where(OutreachMessage.direction=='outbound',OutreachMessage.created_at>=hour)) or 0
        return daily,hourly
    def send_one(self,db,p,campaign=None):
        if self.s.TEST_MODE is False and not self.s.OUTREACH_ENABLED:return False
        if p.opted_out or not p.contact_email:return False
        if db.scalar(select(SuppressionList.id).where(SuppressionList.email==p.contact_email)):return False
        daily,hourly=self._counts(db)
        if daily>=self.s.MAX_DAILY_OUTREACH or hourly>=self.s.MAX_HOURLY_OUTREACH:return False
        subject,body=self.ai.generate_outreach({'company_name':p.company_name,'contact_name':p.contact_name,'founder_name':p.founder_name,'description':p.description},p.service_match or 'presentation design')
        uid='OUT-'+uuid.uuid4().hex
        msg=OutreachMessage(message_uid=uid,prospect_id=p.id,campaign_id=campaign.id if campaign else None,subject=subject,body=body,status='TEST' if self.s.TEST_MODE else 'SENDING')
        db.add(msg); db.flush()
        try:
            ext=self.email.send(p.contact_email,subject,body); msg.external_id=ext; msg.status='SENT' if not self.s.TEST_MODE else 'TEST'; msg.sent_at=datetime.now(timezone.utc); p.last_contacted_at=msg.sent_at
            p.next_followup_at=msg.sent_at+timedelta(hours=self.s.FOLLOWUP_1_DELAY_HOURS)
            for seq,hours in ((1,self.s.FOLLOWUP_1_DELAY_HOURS),(2,self.s.FOLLOWUP_2_DELAY_HOURS)):
                db.add(Followup(prospect_id=p.id,sequence=seq,scheduled_at=msg.sent_at+timedelta(hours=hours)))
            db.commit(); events.event('OUTREACH_SENT',prospect_id=p.id,message_uid=uid); return True
        except Exception as e:
            msg.status='FAILED'; db.commit(); events.event('ERROR',component='outreach',prospect_id=p.id,error=str(e)); return False

    def process_followups(self,db):
        now=datetime.now(timezone.utc); rows=db.scalars(select(Followup).where(Followup.status=='SCHEDULED',Followup.scheduled_at<=now).order_by(Followup.scheduled_at)).all(); sent=0
        for f in rows:
            p=db.get(Prospect,f.prospect_id)
            if not p or p.opted_out or not p.contact_email: f.status='CANCELLED'; continue
            # Stop if prospect replied (reply is recorded as inbound).
            replied=db.scalar(select(OutreachMessage.id).where(OutreachMessage.prospect_id==p.id,OutreachMessage.direction=='inbound'))
            if replied: f.status='CANCELLED'; continue
            if sent>=self.s.FOLLOWUP_MAX_PER_DAY: break
            subject=f'Following up — {p.service_match or "presentation design"}'
            body='Hi, just following up on my note about presentation design support. If this is not relevant, no problem — I will not keep following up.'
            try:
                self.email.send(p.contact_email,subject,body); f.sent_at=now; f.status='SENT'; sent+=1; db.commit()
            except Exception: f.status='FAILED'; db.commit()
        return sent
