import json
import uuid
import os
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Header
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.db.session import get_db
from app.schemas.api import CampaignCreate, OrderCreate, OnboardingUpdate
from app.models.entities import *
from app.services.campaigns import CampaignService
from app.services.flutterwave import FlutterwaveService
from app.services.delivery import DeliveryService
from app.core.config import get_settings
from app.core.logging import events


router = APIRouter(prefix="/api")

s = get_settings()
campaigns = CampaignService()
flw = FlutterwaveService()


def safe_campaign(c):
    return {
        "campaign_id": c.campaign_id,
        "name": c.name,
        "status": c.status,
        "target_prospects": c.target_prospects,
        "completed_prospects": c.completed_prospects,
        "remaining_prospects": c.remaining_prospects,
        "daily_limit": c.daily_limit,
        "priority": c.priority,
        "industries": c.industries,
        "countries": c.countries,
        "services": c.services,
        "start_time": c.start_time,
        "end_time": c.end_time,
    }


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/status")
def status(db: Session = Depends(get_db)):
    c = db.scalar(
        select(Campaign)
        .where(Campaign.status == "RUNNING")
        .order_by(Campaign.created_at.desc())
    )

    return {
        "agent_status": "RUNNING" if c else "IDLE",
        "active_campaign": safe_campaign(c) if c else None,
        "today_prospects": db.scalar(select(func.count(Prospect.id))) or 0,
        "outreach_count": db.scalar(select(func.count(OutreachMessage.id))) or 0,
        "active_orders": db.scalar(
            select(func.count(Order.id)).where(
                Order.status.in_(["PAID", "IN_PRODUCTION", "QC", "READY"])
            )
        ) or 0,
    }


@router.get("/campaigns")
def list_campaigns(db: Session = Depends(get_db)):
    campaigns_list = db.scalars(
        select(Campaign).order_by(Campaign.created_at.desc())
    ).all()

    return [safe_campaign(c) for c in campaigns_list]


@router.post("/campaigns")
def create_campaign(
    payload: CampaignCreate,
    db: Session = Depends(get_db),
):
    c = campaigns.create(
        db,
        payload.name,
        payload.target_prospects,
        payload.duration_days,
        payload.industries,
        payload.countries,
        payload.services,
        payload.priority,
    )

    return safe_campaign(c)


def change(cid, status, db):
    c = campaigns.set_status(db, cid, status)

    if not c:
        raise HTTPException(404, "Campaign not found")

    return safe_campaign(c)


@router.post("/campaigns/{id}/pause")
def pause(id: str, db: Session = Depends(get_db)):
    return change(id, "PAUSED", db)


@router.post("/campaigns/{id}/resume")
def resume(id: str, db: Session = Depends(get_db)):
    return change(id, "RUNNING", db)


@router.post("/campaigns/{id}/stop")
def stop(id: str, db: Session = Depends(get_db)):
    return change(id, "STOPPED", db)


@router.post("/campaigns/{id}/cancel")
def cancel(id: str, db: Session = Depends(get_db)):
    return change(id, "CANCELLED", db)


@router.get("/prospects")
def prospects(
    limit: int = 50,
    db: Session = Depends(get_db),
):
    return [
        {
            "id": p.id,
            "company_name": p.company_name,
            "website": p.website,
            "industry": p.industry,
            "service_match": p.service_match,
            "score": p.qualification_score,
            "status": p.status,
            "email": p.contact_email,
        }
        for p in db.scalars(
            select(Prospect)
            .order_by(Prospect.created_at.desc())
            .limit(min(limit, 200))
        ).all()
    ]


@router.get("/prospects/{id}")
def prospect(
    id: int,
    db: Session = Depends(get_db),
):
    p = db.get(Prospect, id)

    if not p:
        raise HTTPException(404, "Prospect not found")

    return {
        "id": p.id,
        "company_name": p.company_name,
        "website": p.website,
        "industry": p.industry,
        "description": p.description,
        "country": p.country,
        "service_match": p.service_match,
        "qualification": p.qualification_json,
    }


@router.post("/prospects/search")
async def search_prospects(
    payload: dict,
    db: Session = Depends(get_db),
):
    from app.services.prospecting import ProspectingService

    limit = min(
        int(payload.get("limit", 20)),
        getattr(s, "MAX_PROSPECTS_PER_RUN", 20),
    )

    items = await ProspectingService().discover(
        db,
        payload,
        limit,
    )

    return [
        {
            "id": p.id,
            "company_name": p.company_name,
            "service": p.service_match,
            "score": p.qualification_score,
        }
        for p in items
    ]


@router.get("/orders")
def orders(db: Session = Depends(get_db)):
    return [
        {
            "id": o.id,
            "order_id": o.order_id,
            "package": o.package,
            "amount": o.amount,
            "currency": o.currency,
            "status": o.status,
            "created_at": o.created_at,
        }
        for o in db.scalars(
            select(Order).order_by(Order.created_at.desc())
        ).all()
    ]


@router.get("/orders/{id}")
def order(
    id: int,
    db: Session = Depends(get_db),
):
    o = db.get(Order, id)

    if not o:
        raise HTTPException(404, "Order not found")

    return {
        "id": o.id,
        "order_id": o.order_id,
        "package": o.package,
        "amount": o.amount,
        "currency": o.currency,
        "status": o.status,
    }


@router.post("/orders")
async def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
):
    prices = {
        "STARTER": getattr(s, "STARTER_PRICE", 250),
        "PROFESSIONAL": getattr(s, "PROFESSIONAL_PRICE", 500),
        "PREMIUM": getattr(s, "PREMIUM_PRICE", 1000),
    }

    package = payload.package.upper()

    if package not in prices:
        raise HTTPException(400, "Unsupported package")

    cust = Customer(
        name=payload.customer_name,
        company_name=payload.company_name,
        email=payload.email,
        prospect_id=payload.prospect_id,
    )

    db.add(cust)
    db.flush()

    o = Order(
        order_id="PPS-ORD-" + uuid.uuid4().hex[:12].upper(),
        customer_id=cust.id,
        prospect_id=payload.prospect_id,
        package=package,
        amount=prices[package],
        currency=getattr(s, "SERVICE_CURRENCY", "USD"),
        status="PENDING",
    )

    db.add(o)
    db.flush()

    ref = (
        "PPS-"
        + o.order_id
        + "-"
        + uuid.uuid4().hex[:6].upper()
    )

    pay = Payment(
        payment_id="PAY-" + uuid.uuid4().hex[:10],
        order_id=o.id,
        reference=ref,
        amount=o.amount,
        currency=o.currency,
    )

    db.add(pay)
    db.commit()

    try:
        result = await flw.create_payment(
            ref,
            o.amount,
            o.currency,
            payload.email,
            payload.customer_name,
            o.order_id,
        )

        pay.payment_url = result.get("link")
        db.commit()

        events.event(
            "PAYMENT_CREATED",
            order_id=o.order_id,
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(
            502,
            f"Payment creation failed: {e}",
        )

    return {
        "order_id": o.order_id,
        "reference": ref,
        "payment_url": pay.payment_url,
        "amount": o.amount,
        "currency": o.currency,
    }


@router.post("/webhooks/flutterwave")
async def flutterwave_webhook(
    request: Request,
    db: Session = Depends(get_db),
    flutterwave_signature: str | None = Header(
        default=None,
        alias="flutterwave-signature",
    ),
    verif_hash: str | None = Header(
        default=None,
        alias="verif-hash",
    ),
):
    raw = await request.body()

    sig = flutterwave_signature or verif_hash

    if not flw.sign_valid(raw, sig) and not (
        s.TEST_MODE and sig == "TEST"
    ):
        raise HTTPException(
            401,
            "Invalid webhook signature",
        )

    payload = json.loads(raw or b"{}")

    event_id = str(
        payload.get("id")
        or payload.get("webhook_id")
        or hashlib.sha256(raw).hexdigest()
    )

    if db.scalar(
        select(PaymentEvent).where(
            PaymentEvent.event_id == event_id
        )
    ):
        return {
            "status": "ok",
            "duplicate": True,
        }

    ev = PaymentEvent(
        event_id=event_id,
        payload=payload,
    )

    db.add(ev)
    db.commit()

    data = payload.get("data", {})

    txid = data.get("id")
    ref = data.get("tx_ref") or data.get("txRef")

    pay = (
        db.scalar(
            select(Payment).where(
                Payment.reference == ref
            )
        )
        if ref
        else None
    )

    if pay and txid:
        ok, verified = await flw.verify(
            txid,
            pay.reference,
            pay.amount,
            pay.currency,
        )

        if ok:
            pay.status = "PAID"
            pay.provider_transaction_id = str(txid)

            o = db.get(Order, pay.order_id)

            if o:
                o.status = "PAID"

                form = db.scalar(
                    select(OnboardingForm).where(
                        OnboardingForm.order_id == o.id
                    )
                )

                form = form or OnboardingForm(
                    order_id=o.id,
                    data={},
                )

                db.add(form)

            ev.processed = True
            db.commit()

            events.event(
                "PAYMENT_VERIFIED",
                order_id=o.order_id if o else None,
            )

    return {"status": "ok"}


@router.get("/deliveries/{order_id}")
def delivery(
    order_id: int,
    db: Session = Depends(get_db),
):
    d = db.scalar(
        select(Delivery).where(
            Delivery.order_id == order_id
        )
    )

    if not d:
        raise HTTPException(
            404,
            "Delivery not found",
        )

    return {
        "token": d.token,
        "expires_at": d.expires_at,
        "status": d.status,
    }


@router.put("/orders/{id}/onboarding")
def update_onboarding(
    id: int,
    payload: OnboardingUpdate,
    db: Session = Depends(get_db),
):
    o = db.get(Order, id)

    if not o:
        raise HTTPException(
            404,
            "Order not found",
        )

    form = db.scalar(
        select(OnboardingForm).where(
            OnboardingForm.order_id == id
        )
    )

    if not form:
        form = OnboardingForm(
            order_id=id,
            data={},
        )
        db.add(form)

    form.data = {
        **(form.data or {}),
        **payload.data,
    }

    required_fields = [
        "customer_name",
        "company_name",
        "email",
        "presentation_type",
        "purpose",
        "audience",
        "number_of_slides",
        "style",
    ]

    form.status = (
        "COMPLETE"
        if all(
            form.data.get(k) not in (None, "", [])
            for k in required_fields
        )
        else "INCOMPLETE"
    )

    db.commit()

    return {
        "status": form.status,
        "data": form.data,
    }


@router.post("/orders/{id}/files")
async def upload_order_file(
    id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    o = db.get(Order, id)

    if not o:
        raise HTTPException(
            404,
            "Order not found",
        )

    allowed = {
        ".pptx",
        ".ppt",
        ".pdf",
        ".docx",
        ".doc",
        ".txt",
        ".csv",
        ".png",
        ".jpg",
        ".jpeg",
        ".svg",
    }

    ext = os.path.splitext(
        file.filename or ""
    )[1].lower()

    if ext not in allowed:
        raise HTTPException(
            400,
            "Unsupported file type",
        )

    data = await file.read()

    max_upload_mb = getattr(
        s,
        "MAX_UPLOAD_MB",
        25,
    )

    if len(data) > max_upload_mb * 1024 * 1024:
        raise HTTPException(
            413,
            "File too large",
        )

    sha = hashlib.sha256(data).hexdigest()

    base = os.path.join(
        "storage",
        "uploads",
        str(id),
    )

    os.makedirs(
        base,
        exist_ok=True,
    )

    safe = os.path.basename(
        file.filename or "upload"
    )

    path = os.path.join(
        base,
        sha + "_" + safe,
    )

    with open(path, "wb") as f:
        f.write(data)

    uf = UploadedFile(
        order_id=id,
        filename=safe,
        stored_path=path,
        mime_type=file.content_type
        or "application/octet-stream",
        size_bytes=len(data),
        sha256=sha,
    )

    db.add(uf)
    db.commit()

    return {
        "id": uf.id,
        "filename": safe,
        "size_bytes": len(data),
           }
