from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.db.init import init_db
from app.api.routes import router
from app.workers.scheduler import scheduler
from app.telegram.bot import build_bot

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler.start()
    bot = build_bot()
    if bot:
        await bot.initialize()
        await bot.start()
        await bot.updater.start_polling(drop_pending_updates=True)
    yield
    if bot:
        await bot.updater.stop()
        await bot.stop()
        await bot.shutdown()
    scheduler.shutdown(wait=False)

app = FastAPI(title="Pixel Pulse Studio", version="1.0.0", lifespan=lifespan)
app.include_router(router)

@app.get("/")
def root():
    return {"name": "Pixel Pulse Studio", "status": "running"}
