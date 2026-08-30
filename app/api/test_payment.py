from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get("/test-payment/{reference}", response_class=HTMLResponse)
async def test_payment(reference: str):
    return HTMLResponse(f'''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Pixel Pulse Studio Test Payment</title></head><body style="font-family:sans-serif;max-width:600px;margin:40px auto;padding:20px"><h1>Test Payment</h1><p>Reference: <b>{reference}</b></p><p>This is a TEST MODE payment. No money will be charged.</p><p><a href="/payment/test-success/{reference}" style="display:inline-block;padding:14px 20px;background:#111;color:#fff;text-decoration:none;border-radius:8px">Complete Test Payment</a></p></body></html>''')

@router.get("/payment/test-success/{reference}", response_class=HTMLResponse)
async def test_payment_success(reference: str):
    return HTMLResponse(f'''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Payment Complete</title></head><body style="font-family:sans-serif;max-width:600px;margin:40px auto;padding:20px"><h1>✅ Test Payment Complete</h1><p>Reference: <b>{reference}</b></p><p>Return to Telegram and run <b>/orders</b> to check the order.</p></body></html>''')
