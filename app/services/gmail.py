import base64
import json
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.entities import Prospect, Conversation
from app.services.ai import AIService
from app.services.outreach import OutreachService
from app.bot import send_message


class GmailReplyService:
    def __init__(self):
        self.s = get_settings()
        self.ai = AIService()
        self.outreach = OutreachService()

    def configured(self):
        return all((self.s.GMAIL_CLIENT_ID, self.s.GMAIL_CLIENT_SECRET, self.s.GMAIL_REFRESH_TOKEN, self.s.GMAIL_FROM_EMAIL))

    async def _access_token(self):
        if not self.configured():
            raise RuntimeError("Gmail is not configured. Add GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN and GMAIL_FROM_EMAIL.")
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": self.s.GMAIL_CLIENT_ID,
                    "client_secret": self.s.GMAIL_CLIENT_SECRET,
                    "refresh_token": self.s.GMAIL_REFRESH_TOKEN,
                    "grant_type": "refresh_token",
                },
            )
            response.raise_for_status()
            return response.json()["access_token"]

    async def _gmail_get(self, client, token, path, params=None):
        response = await client.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/" + path,
            headers={"Authorization": f"Bearer {token}"},
            params=params or {},
        )
        response.raise_for_status()
        return response.json()

    def _header(self, headers, name):
        wanted = name.lower()
        for item in headers or []:
            if (item.get("name") or "").lower() == wanted:
                return item.get("value") or ""
        return ""

    def _decode_body(self, payload):
        parts = payload.get("parts") or []
        if parts:
            plain = next((p for p in parts if p.get("mimeType") == "text/plain"), None)
            if plain:
                return self._decode_body(plain)
            for part in parts:
                text = self._decode_body(part)
                if text:
                    return text
        data = payload.get("body", {}).get("data")
        if not data:
            return ""
        try:
            return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")
        except Exception:
            return ""

    async def check_replies(self, limit=20):
        token = await self._access_token()
        db = SessionLocal()
        processed = 0
        interested = 0
        skipped = 0
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                listing = await self._gmail_get(
                    client,
                    token,
                    "messages",
                    {"labelIds": "INBOX", "maxResults": str(max(1, min(limit, 50)))}
                )
                for ref in listing.get("messages", []):
                    message = await self._gmail_get(client, token, f"messages/{ref['id']}", {"format": "full"})
                    payload = message.get("payload") or {}
                    headers = payload.get("headers") or []
                    sender = self._header(headers, "From").strip()
                    subject = self._header(headers, "Subject")
                    message_id = message.get("id")
                    body = self._decode_body(payload).strip()
                    if not message_id or not body:
                        skipped += 1
                        continue
                    email = sender.split("<")[-1].split(">", 1)[0].strip().lower() if "<" in sender else sender.strip().lower()
                    if not email or email == self.s.GMAIL_FROM_EMAIL.lower():
                        skipped += 1
                        continue
                    prospect = db.scalar(select(Prospect).where(Prospect.contact_email == email))
                    if not prospect:
                        skipped += 1
                        continue
                    conversation = db.scalar(select(Conversation).where(Conversation.prospect_id == prospect.id))
                    if not conversation:
                        conversation = Conversation(prospect_id=prospect.id, state="OPEN", messages_json=[])
                        db.add(conversation)
                        db.flush()
                    history = list(conversation.messages_json or [])
                    if any(m.get("gmail_message_id") == message_id for m in history if isinstance(m, dict)):
                        skipped += 1
                        continue
                    history.append({
                        "direction": "inbound",
                        "from": email,
                        "subject": subject,
                        "body": body,
                        "gmail_message_id": message_id,
                        "at": datetime.now(timezone.utc).isoformat(),
                    })
                    analysis = self.ai.analyze_reply(
                        {
                            "company_name": prospect.company_name,
                            "contact_name": prospect.contact_name or prospect.founder_name,
                            "contact_email": prospect.contact_email,
                            "service": prospect.service_match,
                        },
                        "\\n\\n".join(f"{m.get('direction','')}: {m.get('body','')}" for m in history[-8:]),
                    )
                    history.append({
                        "direction": "analysis",
                        "interested": analysis.interested,
                        "summary": analysis.summary,
                        "recommended_action": analysis.recommended_action,
                        "requested_slide_count": analysis.requested_slide_count,
                        "presentation_idea": analysis.presentation_idea,
                        "at": datetime.now(timezone.utc).isoformat(),
                    })
                    conversation.messages_json = history
                    conversation.updated_at = datetime.now(timezone.utc)
                    if analysis.interested:
                        prospect.status = "INTERESTED"
                        conversation.state = "OWNER_HANDOFF"
                        interested += 1
                        if self.s.TELEGRAM_ADMIN_CHAT_ID:
                            await send_message(
                                self.s.TELEGRAM_ADMIN_CHAT_ID,
                                f"🔥 INTERESTED CLIENT\\n\\nCompany: {prospect.company_name}\\nContact: {prospect.contact_name or prospect.founder_name or 'Unknown'}\\nEmail: {prospect.contact_email}\\nService: {prospect.service_match or 'Presentation design'}\\nSlides requested: {analysis.requested_slide_count or 'Not provided'}\\nPresentation idea: {analysis.presentation_idea or 'Not provided'}\\n\\nReply:\\n{body[:2500]}\\n\\nGemini: {analysis.summary}\\n\\n👉 Take over and close the deal."
                            )
                    else:
                        reply_subject = subject if subject.lower().startswith("re:") else (f"Re: {subject}" if subject else "Re: Presentation support")
                        reply_message = analysis.reply
                        await self.outreach.send_email(email, reply_subject, reply_message)
                        history.append({"direction": "outbound", "to": email, "subject": reply_subject, "body": reply_message, "at": datetime.now(timezone.utc).isoformat()})
                        conversation.messages_json = history
                    processed += 1
                    db.commit()
            return {"processed": processed, "interested": interested, "skipped": skipped}
        finally:
            db.close()
