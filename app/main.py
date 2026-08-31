import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.db.init import init_db
from app.db.session import SessionLocal
from app.models.entities import Order
from app.api.routes import router
from app.api.telegram import router as telegram_router
from app.api.test_payment import router as test_payment_router
from app.services.presentation import PresentationService
from app.workers.scheduler import scheduler
from app.bot import set_webhook, send_message, webhook_secret
from app.core.config import get_settings

settings = get_settings()
presentations = PresentationService()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if settings.SCHEDULER_ENABLED:
        try:
            scheduler.start()
        except Exception:
            pass
    try:
        await set_webhook()
    except Exception:
        pass
    yield
    if settings.SCHEDULER_ENABLED:
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass

app = FastAPI(
    title="Pixel Pulse Studio",
    version="1.0.0",
    lifespan=lifespan,
)

@app.middleware("http")
async def generate_order_id_fix(request: Request, call_next):
    if request.method == "POST" and request.url.path == "/api/telegram/webhook":
        body = await request.body()
        try:
            update = json.loads(body or b"{}")
            message = update.get("message") or {}
            text = (message.get("text") or "").strip()
            chat_id = (message.get("chat") or {}).get("id")
            command = text.split()[0].split("@")[0].lower() if text else ""
            if command == "/generate":
                if request.headers.get("x-telegram-bot-api-secret-token") != webhook_secret():
                    return JSONResponse({"ok": False, "error": "Invalid Telegram webhook secret"}, status_code=401)
                admin = getattr(settings, "TELEGRAM_ADMIN_CHAT_ID", "")
                if admin and str(chat_id) != str(admin):
                    await send_message(chat_id, "This bot is online, but this chat is not authorized for controls.")
                    return JSONResponse({"ok": True})
                parts = text.split()
                if len(parts) != 2:
                    await send_message(chat_id, "Usage: /generate ORDER_ID\nExample: /generate PPS-ORD-XXXXXXXXXXXX")
                    return JSONResponse({"ok": True})
                value = parts[1]
                db = SessionLocal()
                try:
                    order = db.scalar(select(Order).where(Order.order_id == value))
                    if not order and value.isdigit():
                        order = db.get(Order, int(value))
                    if not order:
                        await send_message(chat_id, "Order not found. Use /orders to see existing order IDs.")
                    elif order.status not in ("PAID", "IN_PRODUCTION", "QC", "READY"):
                        await send_message(chat_id, f"Order {order.order_id} is {order.status}. Payment must be PAID before generation.")
                    else:
                        try:
                            presentation = presentations.generate(db, order.id)
                            slides = len((presentation.strategy_json or {}).get("slides", []))
                            await send_message(chat_id, f"🎨 PRESENTATION READY\nOrder: {order.order_id}\nSlides: {slides}\nPPTX: {settings.BASE_URL}/api/orders/{order.id}/presentation/pptx\nPDF: {settings.BASE_URL}/api/orders/{order.id}/presentation/pdf")
                        except ValueError as e:
                            await send_message(chat_id, str(e))
                        except Exception as e:
                            await send_message(chat_id, f"Presentation generation failed: {e}")
                finally:
                    db.close()
                return JSONResponse({"ok": True})
        except Exception:
            pass
    return await call_next(request)

app.include_router(router)
app.include_router(telegram_router)
app.include_router(test_payment_router)

@app.get("/")
def root():
    return {"name": "Pixel Pulse Studio", "status": "running", "scheduler_enabled": settings.SCHEDULER_ENABLED}
