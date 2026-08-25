from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base

def now(): return datetime.now(timezone.utc)

class Prospect(Base):
    __tablename__="prospects"
    id: Mapped[int]=mapped_column(primary_key=True)
    company_name: Mapped[str]=mapped_column(String(255), index=True)
    website: Mapped[str|None]=mapped_column(String(1000))
    domain: Mapped[str|None]=mapped_column(String(255), index=True)
    industry: Mapped[str|None]=mapped_column(String(120))
    description: Mapped[str|None]=mapped_column(Text)
    country: Mapped[str|None]=mapped_column(String(120), index=True)
    city: Mapped[str|None]=mapped_column(String(120))
    founder_name: Mapped[str|None]=mapped_column(String(255))
    contact_name: Mapped[str|None]=mapped_column(String(255))
    contact_email: Mapped[str|None]=mapped_column(String(320), index=True)
    contact_phone: Mapped[str|None]=mapped_column(String(80))
    public_contact_url: Mapped[str|None]=mapped_column(String(1000))
    linkedin_url: Mapped[str|None]=mapped_column(String(1000))
    source: Mapped[str|None]=mapped_column(String(80))
    source_id: Mapped[str|None]=mapped_column(String(255))
    source_url: Mapped[str|None]=mapped_column(String(1000))
    service_match: Mapped[str|None]=mapped_column(String(120))
    qualification_score: Mapped[int]=mapped_column(Integer, default=0)
    estimated_budget: Mapped[float|None]=mapped_column(Float)
    purchase_likelihood: Mapped[float|None]=mapped_column(Float)
    status: Mapped[str]=mapped_column(String(40), default="NEW", index=True)
    opted_out: Mapped[bool]=mapped_column(Boolean, default=False, index=True)
    qualification_json: Mapped[dict|None]=mapped_column(JSON)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    last_contacted_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    next_followup_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))

class Campaign(Base):
    __tablename__="campaigns"
    id: Mapped[int]=mapped_column(primary_key=True)
    campaign_id: Mapped[str]=mapped_column(String(50), unique=True, index=True)
    name: Mapped[str]=mapped_column(String(255))
    status: Mapped[str]=mapped_column(String(30), default="DRAFT", index=True)
    priority: Mapped[str]=mapped_column(String(20), default="NORMAL")
    target_prospects: Mapped[int]=mapped_column(Integer)
    completed_prospects: Mapped[int]=mapped_column(Integer, default=0)
    remaining_prospects: Mapped[int]=mapped_column(Integer)
    start_time: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    daily_limit: Mapped[int]=mapped_column(Integer)
    industries: Mapped[list]=mapped_column(JSON, default=list)
    countries: Mapped[list]=mapped_column(JSON, default=list)
    services: Mapped[list]=mapped_column(JSON, default=list)
    outreach_limit: Mapped[int]=mapped_column(Integer)
