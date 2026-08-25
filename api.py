from pydantic import BaseModel, Field

class CampaignCreate(BaseModel):
    name: str
    target_prospects: int = Field(gt=0)
    duration_days: int = Field(default=1, gt=0)
    industries: list[str] = []
    countries: list[str] = []
    services: list[str] = []
    priority: str = "NORMAL"
