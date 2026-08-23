from contextlib import asynccontextmanager

from fastapi import FastAPI

from db import init_db
from routes import router
from scheduler import scheduler
from bot import build_bot


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


app = FastAPI(
    title="Pixel Pulse Studio",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/")
async def root():
    return {
        "name": "Pixel Pulse Studio",
        "status": "running",
    }
