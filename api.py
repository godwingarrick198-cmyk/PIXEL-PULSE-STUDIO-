from pydantic import BaseModel, Field
from typing import Optional
class CampaignCreate(BaseModel):
    name:str='Presentation Prospecting'
    target_prospects:int=Field(gt=0,le=100000)
    duration_days:int=Field(default=1,ge=1,le=365)
    industries:list[str]=[]
    countries:list[str]=[]
    services:list[str]=[]
    priority:str='NORMAL'
class OrderCreate(BaseModel):
    customer_name:str
    company_name:str
    email:str
    package:str
    prospect_id:Optional[int]=None
class OnboardingUpdate(BaseModel):
    data:dict
