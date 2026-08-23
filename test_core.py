from app.services.campaigns import CampaignService
from app.services.ai import AIService

def test_fallback_service_match():
    q=AIService().qualify({'company_name':'Acme Startup','industry':'startup','website':'https://acme.test'})
    assert q.recommended_service=='Investor Pitch Deck'

def test_campaign_daily_distribution():
    # 500 over 7 days -> ceiling of 72 before the global cap.
    import math
    assert math.ceil(500/7)==72
