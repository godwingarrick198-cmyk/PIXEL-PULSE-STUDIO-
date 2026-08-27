import re
from urllib.parse import urlparse, urljoin
import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select, or_, func
from app.models.entities import Prospect, SuppressionList
from app.providers import OSMProvider, WebDiscoveryProvider, ProductHuntProvider
from app.services.ai import AIService
from app.core.config import get_settings
from app.core.logging import events

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
SOCIAL_HOSTS = {'facebook.com','linkedin.com','instagram.com','youtube.com','x.com','twitter.com'}

class ProspectingService:
    def __init__(self):
        self.s=get_settings(); self.ai=AIService(); self.providers=[WebDiscoveryProvider(),OSMProvider(),ProductHuntProvider()]

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

    async def _enrich_public_contact(self, raw):
        """Find a real public website/email; never invent an address."""
        if raw.get('contact_email') and raw.get('website'):
            return raw
        s=self.s
        name=(raw.get('company_name') or '').strip()
        country=(raw.get('country') or '').strip()
        website=raw.get('website')
        headers={'User-Agent':s.PUBLIC_WEB_USER_AGENT}
        timeout=httpx.Timeout(12.0)
        try:
            async with httpx.AsyncClient(timeout=timeout,headers=headers,follow_redirects=True) as client:
                # If the provider gave no site, use a public search result to locate one.
                if not website and name and s.WEB_DISCOVERY_ENABLED:
                    q=f'"{name}" {country} official website'
                    r=await client.get('https://html.duckduckgo.com/html/',params={'q':q})
                    if r.is_success:
                        soup=BeautifulSoup(r.text,'html.parser')
                        for a in soup.select('a.result__a'):
                            href=a.get('href',''); p=urlparse(href)
                            dom=p.netloc.lower().removeprefix('www.')
                            if p.scheme in ('http','https') and dom and not any(dom==x or dom.endswith('.'+x) for x in SOCIAL_HOSTS):
                                website=f'{p.scheme}://{p.netloc}'; break
                if not website: return raw
                raw['website']=website
                raw['domain']=self.normalize_domain(website)
                candidates=[website]
                base=website.rstrip('/')
                for path in ('/contact','/contact-us','/about','/team'):
                    candidates.append(urljoin(base,path))
                for url in candidates:
                    try:
                        r=await client.get(url)
                        if not r.is_success: continue
                        text=r.text
                        soup=BeautifulSoup(text,'html.parser')
                        found=[]
                        for a in soup.select('a[href^="mailto:"]'):
                            found.append(a.get('href','')[7:].split('?')[0])
                        found += EMAIL_RE.findall(soup.get_text(' ',strip=True))
                        for email in found:
                            email=email.strip().lower().strip('.,;:()[]<>')
                            if '@' in email and not email.endswith(('.png','.jpg','.jpeg','.svg')):
                                raw['contact_email']=email
                                raw['public_contact_url']=url
                                return raw
                    except Exception:
                        continue
        except Exception as e:
            events.event('ERROR',component='public_contact_enrichment',error=str(e))
        return raw

    async def discover(self,db,query,limit):
        all_items=[]
        for provider in self.providers:
            try: all_items.extend(await provider.discover_prospects(query))
            except Exception as e: events.event('ERROR',component='provider',provider=provider.name,error=str(e))
            if len(all_items)>=limit*3: break
        saved=[]; seen=set()
        for raw in all_items:
            raw=await self._enrich_public_contact(dict(raw))
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
