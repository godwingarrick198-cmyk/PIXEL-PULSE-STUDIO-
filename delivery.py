import secrets
from datetime import datetime, timezone, timedelta
from app.models.entities import Delivery
from app.core.config import get_settings

class DeliveryService:
    def __init__(self): self.s=get_settings()
