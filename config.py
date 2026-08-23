from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')
    GEMINI_API_KEY: str = ''
    TELEGRAM_BOT_TOKEN: str = ''
    TELEGRAM_CHAT_ID: str = ''
    BUSINESS_NAME: str = 'Pixel Pulse Studio'
    BUSINESS_EMAIL: str = ''
    BUSINESS_WEBSITE: str = ''
    SMTP_HOST: str = ''
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ''
    SMTP_PASSWORD: str = ''
    EMAIL_FROM: str = ''
    EMAIL_FROM_NAME: str = 'Pixel Pulse Studio'
    IMAP_HOST: str = ''
    IMAP_PORT: int = 993
    IMAP_USERNAME: str = ''
    IMAP_PASSWORD: str = ''
    FLW_PUBLIC_KEY: str = ''
    FLW_SECRET_KEY: str = ''
    FLW_SECRET_HASH: str = ''
    FLW_BASE_URL: str = 'https://api.flutterwave.com/v3'
    PRODUCT_HUNT_ENABLED: bool = False
    PRODUCT_HUNT_ACCESS_TOKEN: str = ''
    PRODUCT_HUNT_COMMERCIAL_APPROVED: bool = False
    DATABASE_URL: str = 'sqlite:///./pixel_pulse.db'
    BASE_URL: str = ''
    FULL_AUTO: bool = False
    TEST_MODE: bool = True
    SERVICE_CURRENCY: str = 'USD'
    STARTER_PRICE: float = 250
    PROFESSIONAL_PRICE: float = 500
    PREMIUM_PRICE: float = 1000
    MAX_PROSPECTS_PER_RUN: int = 20
    MAX_DAILY_PROSPECTS: int = 100
    MAX_DAILY_OUTREACH: int = 25
    MAX_HOURLY_OUTREACH: int = 5
    FOLLOWUP_MAX_PER_DAY: int = 25
    MIN_MESSAGE_DELAY_SECONDS: int = 20
    PROSPECT_INTERVAL_MINUTES: int = 15
    FOLLOWUP_INTERVAL_MINUTES: int = 30
    PAYMENT_CHECK_INTERVAL_MINUTES: int = 15
    FOLLOWUP_1_DELAY_HOURS: int = 48
    FOLLOWUP_2_DELAY_HOURS: int = 120
    MIN_QUALIFICATION_SCORE: int = 80
    MIN_PRESENTATION_QUALITY_SCORE: int = 90
    MAX_AUTO_REPAIR_ATTEMPTS: int = 2
    MAX_UPLOAD_MB: int = 25
    DELIVERY_TOKEN_TTL_HOURS: int = 168
    PUBLIC_WEB_USER_AGENT: str = 'PixelPulseStudio/1.0 (+https://example.com)'
    WEB_DISCOVERY_ENABLED: bool = True
    OSM_ENABLED: bool = True
    OUTREACH_ENABLED: bool = True
    SCHEDULER_ENABLED: bool = True

@lru_cache
def get_settings() -> Settings:
    return Settings()
