import asyncio
import base64
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage

import aiosmtplib
import httpx
from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import events
from app.models.entities import Prospect, Campaign, CampaignProspect, OutreachMessage, SuppressionList
from app.services.ai import AIService


class OutreachService:
    def __init__(self):
        self.s = get_settings()
        self.ai = AIService()

    async def send_email_gmail_api(self, to_email, subject, body):
        if not self.s.GMAIL_CLIENT_ID or not self.s.GMAIL_CLIENT_SECRET or not self.s.GMAIL_REFRESH_TOKEN:
            raise RuntimeError("Gmail API credentials are not configured")

        sender = self.s.GMAIL_FROM_EMAIL or self.s.SMTP_FROM_EMAIL or self.s.SMTP_USERNAME
        if not sender:
            raise RuntimeError("GMAIL_FROM_EMAIL is not configured")

        # Refresh the short-lived Gmail access token over HTTPS.
        async with httpx.AsyncClient(timeout=20.0) as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": self.s.GMAIL_CLIENT_ID,
                    "client_secret": self.s.GMAIL_CLIENT_SECRET,
                    "refresh_token": self.s.GMAIL_REFRESH_TOKEN,
                    "grant_type": "refresh_token",
                },
            )
            token_response.raise_for_status()
            access_token = token_response.json().get("access_token")
            if not access_token:
                raise RuntimeError("Google did not return an access token")

            msg = EmailMessage()
            msg["From"] = sender
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.set_content(body)
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode().rstrip("=")

            response = await client.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"raw": raw},
            )
            response.raise_for_status()

    async def send_email_smtp(self, to_email, subject, body):
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

        configured_port = int(self.s.SMTP_PORT or 587)
        attempts = [(465, True)] if configured_port == 465 else [(587, False), (465, True)]
        last_error = None
        for port, implicit_tls in attempts:
            try:
                kwargs = {
                    "hostname": self.s.SMTP_HOST,
                    "port": port,
                    "username": self.s.SMTP_USERNAME,
                    "password": self.s.SMTP_PASSWORD,
                    "timeout": timeout,
                    "start_tls": not implicit_tls,
                    "use_tls": implicit_tls,
                }
                await asyncio.wait_for(aiosmtplib.send(msg, **kwargs), timeout=timeout + 5)
                return
            except Exception as exc:
                last_error = exc
                events.event("SMTP_ATTEMPT_FAILED", host=self.s.SMTP_HOST, port=port, error=str(exc))
        raise RuntimeError(
            f"Unable to connect to {self.s.SMTP_HOST} on SMTP ports "
            f"{', '.join(str(p) for p, _ in attempts)}: {last_error}"
        )

    async def send_email(self, to_email, subject, body):
        if not to_email:
            raise ValueError("Prospect has no email address")

        # Prefer Gmail's HTTPS API on Render. This avoids the SMTP port timeout
        # that was blocking outreach. SMTP remains available as a fallback only
        # when Gmail API credentials have not been configured.
        if self.s.GMAIL_CLIENT_ID and self.s.GMAIL_CLIENT_SECRET and self.s.GMAIL_REFRESH_TOKEN:
            try:
                await self.send_email_gmail_api(to_email, subject, body)
                events.event("GMAIL_API_SENT", recipient=to_email)
                return
            except Exception as exc:
                events.event("GMAIL_API_FAILED", recipient=to_email, error=str(exc))
                raise RuntimeError(f"Gmail API delivery failed: {exc}") from exc

        await self.send_email_smtp(to_email, subject, body)

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

        # Automatic/background outreach never retries a failed or contacted lead.
        # An explicit /outreach CAMPAIGN_ID PROSPECT_ID request is a deliberate retry.
        explicit_retry = cp and cp.status == "FAILED"
        if cp and cp.status in ("CONTACTED", "SUPPRESSED"):
            return {"status": "SKIPPED", "reason": cp.status.lower(), "prospect_id": prospect.id}
        if explicit_retry:
            cp.status = "QUEUED"
            db.commit()

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
