import json
import logging
import sys
from datetime import datetime, timezone


logger = logging.getLogger("pixel_pulse_studio")

if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s"
        )
    )
    logger.addHandler(handler)

logger.setLevel(logging.INFO)


class EventLogger:
    def event(self, event_name: str, **data):
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event_name,
            **data,
        }

        logger.info(json.dumps(payload, default=str))


events = EventLogger()
