from pydantic import BaseModel, Field


class CampaignCreate(BaseModel):
    name: str
    target_prospects: int = Field(ge=1)
    duration_days: int = Field(default=1, ge=1)
    industries: list[str] = []
    countries: list[str] = []
    services: list[str] = []
    priority: str = "NORMAL"


class OrderCreate(BaseModel):
    package: str
    customer_name: str
    company_name: str | None = None
    email: str
    prospect_id: int | None = None


class OnboardingUpdate(BaseModel):
    data: dict
