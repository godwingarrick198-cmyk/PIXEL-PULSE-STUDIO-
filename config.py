from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    DATABASE_URL: str = "sqlite:///./pixel_pulse.db"
    GEMINI_API_KEY: str = ""
    FLW_SECRET_KEY: str = ""
    FLW_SECRET_HASH: str = ""
    FLW_BASE_URL: str = "https://api.flutterwave.com/v3"
    BASE_URL: str = ""
    SERVICE_CURRENCY: str = "USD"
    STARTER_PRICE: float = 250
    PROFESSIONAL_PRICE: float = 500
    PREMIUM_PRICE: float = 1000
    TEST_MODE: bool = True
    MAX_PROSPECTS_PER_RUN: int = 20
    MAX_DAILY_PROSPECTS: int = 20
    MAX_DAILY_OUTREACH: int = 20
    MIN_QUALIFICATION_SCORE: int = 70
    MAX_UPLOAD_MB: int = 20
    DELIVERY_TOKEN_TTL_HOURS: int = 168

_settings = None
def get_settings():
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
