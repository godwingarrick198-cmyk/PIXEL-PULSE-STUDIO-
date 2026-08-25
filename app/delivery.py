import secrets
from datetime import datetime, timezone, timedelta
from app.models.entities import Delivery
from app.core.config import get_settings


class DeliveryService:
    def __init__(self):
        self.s = get_settings()

    def create(self, db, order_id):
        d = Delivery(
            order_id=order_id,
            token=secrets.token_urlsafe(32),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=self.s.DELIVERY_TOKEN_TTL_HOURS),
        )
        db.add(d)
        db.commit()
        db.refresh(d)
        return d
