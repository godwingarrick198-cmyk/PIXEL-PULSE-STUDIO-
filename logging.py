import logging
logger = logging.getLogger("pixel_pulse")

class EventLogger:
    def event(self, name, **data):
        logger.info("%s %s", name, data)

events = EventLogger()
