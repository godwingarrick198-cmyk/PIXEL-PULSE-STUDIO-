from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy import select
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.entities import Prospect, OutreachMessage, Conversation
from app.services.ai import AIService
from app.services.outreach import OutreachService
from app.bot import send_message

router=APIRouter(prefix="/api/brevo")
settings=get_settings()
ai=AIService()
outreach=OutreachService()

def mailbox(value):
    if isinstance(value,dict):
        return (value.get("Address") or value.get("address") or value.get("email") or "").strip().lower()
    return str(value or "").strip().lower()

@router.post("/inbound")
async def brevo_inbound(request:Request):
    if not settings.BREVO_REPLY_DOMAIN:
        raise HTTPException(503,"BREVO_REPLY_DOMAIN is not configured")
    payload=await request.json()
    items=payload.get("items") if isinstance(payload,dict) else None
    if not isinstance(items,list):
        items=[payload] if isinstance(payload,dict) else []
    db=SessionLocal()
    try:
        processed=0
        interested=0
        for item in items:
            sender=mailbox(item.get("From") or item.get("from"))
            subject=item.get("Subject") or item.get("subject") or ""
            body=item.get("ExtractedMarkdownMessage") or item.get("RawTextBody") or item.get("RawHtmlBody") or ""
            in_reply_to=item.get("InReplyTo") or item.get("inReplyTo")
            if not sender or not body:
                continue
            prospect=db.scalar(select(Prospect).where(Prospect.contact_email==sender))
            if not prospect and in_reply_to:
                original=db.scalar(select(OutreachMessage).where(OutreachMessage.external_id==in_reply_to))
                if original:
                    prospect=db.get(Prospect,original.prospect_id)
            if not prospect:
                continue
            conversation=db.scalar(select(Conversation).where(Conversation.prospect_id==prospect.id))
            if not conversation:
                conversation=Conversation(prospect_id=prospect.id,state="OPEN",messages_json=[])
                db.add(conversation)
                db.flush()
            history=list(conversation.messages_json or [])
            history.append({"direction":"inbound","from":sender,"subject":subject,"body":body,"at":datetime.now(timezone.utc).isoformat()})
            analysis=ai.analyze_reply(
                {"company_name":prospect.company_name,"contact_name":prospect.contact_name or prospect.founder_name,"contact_email":prospect.contact_email,"service":prospect.service_match},
                "\n\n".join(f"{m.get('direction','')}: {m.get('body','')}" for m in history[-8:])
            )
            history.append({"direction":"analysis","interested":analysis.interested,"summary":analysis.summary,"recommended_action":analysis.recommended_action,"at":datetime.now(timezone.utc).isoformat()})
            conversation.messages_json=history
            conversation.updated_at=datetime.now(timezone.utc)
            if analysis.interested:
                prospect.status="INTERESTED"
                conversation.state="OWNER_HANDOFF"
                interested+=1
                if settings.TELEGRAM_ADMIN_CHAT_ID:
                    await send_message(settings.TELEGRAM_ADMIN_CHAT_ID,f"🔥 INTERESTED CLIENT\n\nCompany: {prospect.company_name}\nContact: {prospect.contact_name or prospect.founder_name or 'Unknown'}\nEmail: {prospect.contact_email}\nService: {prospect.service_match or 'Presentation design'}\n\nReply:\n{body[:2500]}\n\nGemini: {analysis.summary}\n\n👉 Take over and close the deal.")
            else:
                reply_subject=subject if subject.lower().startswith("re:") else f"Re: {subject}" if subject else "Re: Presentation support"
                reply_message=analysis.reply
                await outreach.send_email(sender,reply_subject,reply_message)
                history.append({"direction":"outbound","to":sender,"subject":reply_subject,"body":reply_message,"at":datetime.now(timezone.utc).isoformat()})
            processed+=1
            db.commit()
        return {"ok":True,"processed":processed,"interested":interested}
    finally:
        db.close()
