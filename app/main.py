from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.db.init import init_db
from app.api.routes import router
from app.api.telegram import router as telegram_router
from app.api.test_payment import router as test_payment_router
from app.workers.scheduler import scheduler
from app.bot import set_webhook
from app.core.config import get_settings

settings = get_settings()

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

app.include_router(router)
app.include_router(telegram_router)
app.include_router(test_payment_router)

@app.get("/")
def root():
    return {"name": "Pixel Pulse Studio", "status": "running", "scheduler_enabled": settings.SCHEDULER_ENABLED}
