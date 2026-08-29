import asyncio
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage

import aiosmtplib
from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import events
from app.models.entities import Prospect, Campaign, CampaignProspect, OutreachMessage, SuppressionList
from app.services.ai import AIService


class OutreachService:
    def __init__(self):
        self.s = get_settings()
        self.ai = AIService()

    async def send_email(self, to_email, subject, body):
        if not to_email:
            raise ValueError("Prospect has no email address")
        if not self.s.SMTP_USERNAME or not self.s.SMTP_PASSWORD:
            raise RuntimeError("Gmail SMTP credentials are not configured")

        msg = EmailMessage()
        msg["From"] = self.s.SMTP_FROM_EMAIL or self.s.SMTP_USERNAME
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)

        try:
            timeout = float(getattr(self.s, "SMTP_TIMEOUT_SECONDS", 20))
        except (TypeError, ValueError):
            timeout = 20.0
        timeout = max(5.0, min(timeout, 60.0))

        await asyncio.wait_for(
            aiosmtplib.send(
                msg,
                hostname=self.s.SMTP_HOST,
                port=self.s.SMTP_PORT,
                start_tls=True,
                username=self.s.SMTP_USERNAME,
                password=self.s.SMTP_PASSWORD,
                timeout=timeout,
            ),
            timeout=timeout + 5,
        )

    def suppressed(self, db, prospect):
        email = (prospect.contact_email or "").lower() if prospect.contact_email else None
        domain = prospect.domain
        if prospect.opted_out:
            return True
        if email and domain:
            q = select(SuppressionList.id).where(
                (SuppressionList.email == email) | (SuppressionList.domain == domain)
            )
        elif email:
            q = select(SuppressionList.id).where(SuppressionList.email == email)
        elif domain:
            q = select(SuppressionList.id).where(SuppressionList.domain == domain)
        else:
            return False
        return db.scalar(q) is not None

    async def send_one(self, db, campaign_code, prospect_id):
        campaign = db.scalar(select(Campaign).where(Campaign.campaign_id == campaign_code))
        prospect = db.get(Prospect, prospect_id)
        if not campaign or not prospect:
            raise ValueError("Campaign or prospect not found")

        cp = db.scalar(select(CampaignProspect).where(
            CampaignProspect.campaign_id == campaign.id,
            CampaignProspect.prospect_id == prospect.id,
        ))

        if self.suppressed(db, prospect):
            if cp:
                cp.status = "SUPPRESSED"
                db.commit()
            return {"status": "SKIPPED", "reason": "suppressed", "prospect_id": prospect.id}

        # A failed or already-contacted prospect is never retried automatically.
        if cp and cp.status in ("FAILED", "CONTACTED", "SUPPRESSED"):
            return {"status": "SKIPPED", "reason": cp.status.lower(), "prospect_id": prospect.id}

        subject, body = self.ai.generate_outreach(
            prospect.__dict__, prospect.service_match or "presentation design"
        )
        uid = "PPS-MSG-" + uuid.uuid4().hex[:12].upper()
        row = OutreachMessage(
            message_uid=uid,
            prospect_id=prospect.id,
            campaign_id=campaign.id,
            channel="email",
            direction="outbound",
            subject=subject,
            body=body,
            status="QUEUED",
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        try:
            await self.send_email(prospect.contact_email, subject, body)
            row.status = "SENT"
            row.sent_at = datetime.now(timezone.utc)
            prospect.last_contacted_at = row.sent_at
            if cp:
                cp.status = "CONTACTED"
            db.commit()
            events.event("OUTREACH_SENT", prospect_id=prospect.id, campaign_id=campaign.campaign_id, message_id=uid)
            return {"status": "SENT", "prospect_id": prospect.id, "message_id": uid, "company_name": prospect.company_name}
        except Exception as e:
            row.status = "FAILED"
            if cp:
                cp.status = "FAILED"
            db.commit()
            events.event("ERROR", component="outreach_send", error=str(e), prospect_id=prospect.id)
            return {"status": "FAILED", "prospect_id": prospect.id, "message_id": uid, "error": str(e)}
