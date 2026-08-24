import logging, json
from datetime import datetime, timezone

logger = logging.getLogger('pixel_pulse')

class EventLogger:
    def __init__(self):
        self.log = logger
    def event(self, event: str, **fields):
        payload = {'timestamp': datetime.now(timezone.utc).isoformat(), 'event': event, **fields}
        self.log.info(json.dumps(payload, default=str, separators=(',', ':')))

events = EventLogger()
