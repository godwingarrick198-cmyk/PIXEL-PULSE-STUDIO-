from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.db.init import init_db
from app.api.routes import router
from app.workers.scheduler import scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    try:
        scheduler.start()
    except Exception:
        pass
    yield
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


@app.get("/")
def root():
    return {"name": "Pixel Pulse Studio", "status": "running"}
