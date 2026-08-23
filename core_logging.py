import json
import logging
from datetime import datetime, timezone


logger = logging.getLogger("pixel_pulse")


class EventLogger:

    def event(self, event, **fields):
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **fields,
        }

        logger.info(
            json.dumps(
                payload,
                default=str,
            )
        )


events = EventLogger()
