import os
from dataclasses import dataclass

def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}

@dataclass(frozen=True)
class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./pixel_pulse.db")
    BASE_URL: str = os.getenv("BASE_URL", "")
    SERVICE_CURRENCY: str = os.getenv("SERVICE_CURRENCY", "NGN")
    STARTER_PRICE: float = float(os.getenv("STARTER_PRICE", "250"))
    PROFESSIONAL_PRICE: float = float(os.getenv("PROFESSIONAL_PRICE", "500"))
    PREMIUM_PRICE: float = float(os.getenv("PREMIUM_PRICE", "1000"))
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    FLW_SECRET_KEY: str = os.getenv("FLW_SECRET_KEY", "")
    FLW_SECRET_HASH: str = os.getenv("FLW_SECRET_HASH", "")
    FLW_BASE_URL: str = os.getenv("FLW_BASE_URL", "https://api.flutterwave.com/v3")
    TEST_MODE: bool = _bool("TEST_MODE", False)
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    OSM_ENABLED: bool = _bool("OSM_ENABLED", True)
    WEB_DISCOVERY_ENABLED: bool = _bool("WEB_DISCOVERY_ENABLED", False)
    PRODUCT_HUNT_ENABLED: bool = _bool("PRODUCT_HUNT_ENABLED", False)
    PRODUCT_HUNT_ACCESS_TOKEN: str = os.getenv("PRODUCT_HUNT_ACCESS_TOKEN", "")
    PRODUCT_HUNT_COMMERCIAL_APPROVED: bool = _bool("PRODUCT_HUNT_COMMERCIAL_APPROVED", False)
    PUBLIC_WEB_USER_AGENT: str = os.getenv("PUBLIC_WEB_USER_AGENT", "PixelPulseStudio/1.0")
    MAX_PROSPECTS_PER_RUN: int = int(os.getenv("MAX_PROSPECTS_PER_RUN", "50"))
    MIN_QUALIFICATION_SCORE: int = int(os.getenv("MIN_QUALIFICATION_SCORE", "60"))
    MAX_DAILY_PROSPECTS: int = int(os.getenv("MAX_DAILY_PROSPECTS", "100"))
    MAX_DAILY_OUTREACH: int = int(os.getenv("MAX_DAILY_OUTREACH", "100"))
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "20"))
    DELIVERY_TOKEN_TTL_HOURS: int = int(os.getenv("DELIVERY_TOKEN_TTL_HOURS", "72"))

_settings = Settings()
def get_settings() -> Settings: return _settings
