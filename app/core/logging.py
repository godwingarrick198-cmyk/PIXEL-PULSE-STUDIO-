import logging
from typing import Any

_logger = logging.getLogger("pixel_pulse")
if not _logger.handlers:
    logging.basicConfig(level=logging.INFO)


class EventLogger:
    def event(self, name: str, **data: Any) -> None:
        _logger.info("%s %s", name, data)


events = EventLogger()
