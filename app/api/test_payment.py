from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.entities import Order, Payment

router = APIRouter()


@router.get("/test-payment/{reference}", response_class=HTMLResponse)
async def test_payment(reference: str):
    return HTMLResponse(
        f'''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Pixel Pulse Studio Test Payment</title></head><body style="font-family:sans-serif;max-width:600px;margin:40px auto;padding:20px"><h1>Test Payment</h1><p>Reference: <b>{reference}</b></p><p>This is a TEST MODE payment. No money will be charged.</p><p><a href="/payment/test-success/{reference}" style="display:inline-block;padding:14px 20px;background:#111;color:#fff;text-decoration:none;border-radius:8px">Complete Test Payment</a></p></body></html>'''
    )


@router.get("/payment/test-success/{reference}", response_class=HTMLResponse)
async def test_payment_success(reference: str):
    db = SessionLocal()
    try:
        payment = db.scalar(select(Payment).where(Payment.reference == reference))
        if not payment:
            return HTMLResponse(
                "<h1>Payment reference not found</h1><p>This test payment does not match an existing order.</p>",
                status_code=404,
            )

        order = db.get(Order, payment.order_id)
        if not order:
            return HTMLResponse(
                "<h1>Order not found</h1><p>The payment exists but its order could not be found.</p>",
                status_code=404,
            )

        payment.status = "PAID"
        payment.provider_transaction_id = f"TEST-{reference}"
        order.status = "PAID"
        db.commit()

        return HTMLResponse(
            f'''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Payment Complete</title></head><body style="font-family:sans-serif;max-width:600px;margin:40px auto;padding:20px"><h1>✅ Test Payment Complete</h1><p>Order: <b>{order.order_id}</b></p><p>Payment status: <b>PAID</b></p><p>No money was charged. Return to Telegram and run <b>/orders</b>.</p></body></html>'''
        )
    finally:
        db.close()
