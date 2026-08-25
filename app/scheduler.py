try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    scheduler = AsyncIOScheduler()
except Exception:
    class _NoopScheduler:
        def start(self): pass
        def shutdown(self, wait=False): pass
    scheduler = _NoopScheduler()
