from urllib.parse import urlparse
from sqlalchemy import select, or_, func
from app.models.entities import Prospect, SuppressionList
from app.providers import OSMProvider, WebDiscoveryProvider, ProductHuntProvider
from app.services.ai import AIService
from app.core.config import get_settings
from app.core.logging import events

class ProspectingService:
    def __init__(self): self.s=get_settings(); self.ai=AIService(); self.providers=[WebDiscoveryProvider(),OSMProvider(),ProductHuntProvider()]
    def normalize_domain(self,url):
        if not url: return None
        try: return urlparse(url if '://' in url else 'https://'+url).netloc.lower().removeprefix('www.').split(':')[0]
        except Exception: return None
    def suppressed(self,db,p):
        dom=self.normalize_domain(p.get('website') or p.get('domain')); email=(p.get('contact_email') or '').lower(); company=p.get('company_name','')
        clauses=[]
        if email: clauses.append(SuppressionList.email==email)
        if dom: clauses.append(SuppressionList.domain==dom)
        if company: clauses.append(SuppressionList.company.ilike(company))
        return bool(clauses and db.scalar(select(SuppressionList.id).where(or_(*clauses))))
    async def discover(self,db,query,limit):
        all_items=[]
        for provider in self.providers:
            try: all_items.extend(await provider.discover_prospects(query))
            except Exception as e: events.event('ERROR',component='provider',provider=provider.name,error=str(e))
            if len(all_items)>=limit*2: break
        saved=[]; seen=set()
        for raw in all_items:
            domain=self.normalize_domain(raw.get('website') or raw.get('domain')); email=(raw.get('contact_email') or '').strip().lower(); name=(raw.get('company_name') or '').strip()
            key=domain or email or name.lower() or str(raw.get('source_id') or '')
            if not key or key in seen: continue
            seen.add(key)
            checks=[]
            if domain: checks.append(Prospect.domain==domain)
            if email: checks.append(Prospect.contact_email==email)
            if name: checks.append(func.lower(Prospect.company_name)==name.lower())
            if checks and db.scalar(select(Prospect).where(or_(*checks))): continue
            if self.suppressed(db,raw): continue
            q=self.ai.qualify({**raw,'domain':domain})
            if not q.qualified or q.score < self.s.MIN_QUALIFICATION_SCORE or q.recommended_service=='SKIP': continue
            p=Prospect(company_name=name or 'Unknown',website=raw.get('website'),domain=domain,industry=raw.get('industry') or q.company_type,description=raw.get('description'),country=raw.get('country'),city=raw.get('city'),founder_name=raw.get('founder_name'),contact_name=raw.get('contact_name'),contact_email=email or None,contact_phone=raw.get('contact_phone'),public_contact_url=raw.get('public_contact_url'),linkedin_url=raw.get('linkedin_url'),source=raw.get('source'),source_id=str(raw.get('source_id') or ''),source_url=raw.get('source_url'),service_match=q.recommended_service,qualification_score=q.score,estimated_budget=q.estimated_budget,purchase_likelihood=q.purchase_likelihood,status='QUALIFIED',qualification_json=q.model_dump())
            db.add(p); db.flush(); saved.append(p); events.event('PROSPECT_QUALIFIED',prospect_id=p.id,score=q.score)
            if len(saved)>=limit: break
        db.commit(); return saved
