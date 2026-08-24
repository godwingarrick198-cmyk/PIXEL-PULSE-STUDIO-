import os
from functools import lru_cache


class Settings:
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite:///./pixel_pulse.db",
    )

    TEST_MODE: bool = os.getenv("TEST_MODE", "true").lower() == "true"

    BASE_URL: str = os.getenv("BASE_URL", "")

    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "")
    EMAIL_FROM_NAME: str = os.getenv(
        "EMAIL_FROM_NAME",
        "Pixel Pulse Studio",
    )

    IMAP_HOST: str = os.getenv("IMAP_HOST", "")
    IMAP_PORT: int = int(os.getenv("IMAP_PORT", "993"))
    IMAP_USERNAME: str = os.getenv("IMAP_USERNAME", "")
    IMAP_PASSWORD: str = os.getenv("IMAP_PASSWORD", "")

    FLW_SECRET_KEY: str = os.getenv("FLW_SECRET_KEY", "")
    FLW_SECRET_HASH: str = os.getenv("FLW_SECRET_HASH", "")
    FLW_BASE_URL: str = os.getenv(
        "FLW_BASE_URL",
        "https://api.flutterwave.com/v3",
    )

    OSM_ENABLED: bool = os.getenv(
        "OSM_ENABLED",
        "true",
    ).lower() == "true"

    PUBLIC_WEB_USER_AGENT: str = os.getenv(
        "PUBLIC_WEB_USER_AGENT",
        "Pixel Pulse Studio/1.0",
    )

    OUTREACH_ENABLED: bool = os.getenv(
        "OUTREACH_ENABLED",
        "false",
    ).lower() == "true"

    MAX_DAILY_PROSPECTS: int = int(
        os.getenv("MAX_DAILY_PROSPECTS", "20")
    )

    MAX_DAILY_OUTREACH: int = int(
        os.getenv("MAX_DAILY_OUTREACH", "20")
    )

    MAX_HOURLY_OUTREACH: int = int(
        os.getenv("MAX_HOURLY_OUTREACH", "5")
    )

    FOLLOWUP_1_DELAY_HOURS: int = int(
        os.getenv("FOLLOWUP_1_DELAY_HOURS", "48")
    )

    FOLLOWUP_2_DELAY_HOURS: int = int(
        os.getenv("FOLLOWUP_2_DELAY_HOURS", "120")
    )

    FOLLOWUP_MAX_PER_DAY: int = int(
        os.getenv("FOLLOWUP_MAX_PER_DAY", "20")
    )

    DELIVERY_TOKEN_TTL_HOURS: int = int(
        os.getenv("DELIVERY_TOKEN_TTL_HOURS", "72")
    )

    MIN_QUALIFICATION_SCORE: int = int(
        os.getenv("MIN_QUALIFICATION_SCORE", "70")
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
