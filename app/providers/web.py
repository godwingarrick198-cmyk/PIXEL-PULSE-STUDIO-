import re, urllib.parse, httpx
from bs4 import BeautifulSoup
from app.core.config import get_settings
from app.providers.base import ProspectProvider
from app.core.logging import events

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
CONTACT_PATHS = ('/contact', '/contact-us', '/about', '/about-us', '/team')
BLOCKED_EMAIL_DOMAINS = {'example.com', 'example.org', 'example.net'}

class WebDiscoveryProvider(ProspectProvider):
    name='web'

    async def _public_email(self, client, website):
        base = website.rstrip('/')
        urls = [base] + [base + p for p in CONTACT_PATHS]
        seen = set()
        for url in urls:
            if url in seen: continue
            seen.add(url)
            try:
                r = await client.get(url, follow_redirects=True)
                if r.status_code >= 400: continue
                html = r.text[:500000]
                soup = BeautifulSoup(html, 'html.parser')
                for a in soup.select('a[href^="mailto:"]'):
                    email = a.get('href','')[7:].split('?')[0].strip().lower()
                    if EMAIL_RE.fullmatch(email) and email.split('@')[-1] not in BLOCKED_EMAIL_DOMAINS:
                        return email
                for email in EMAIL_RE.findall(soup.get_text(' ', strip=True)):
                    email = email.lower()
                    if email.split('@')[-1] not in BLOCKED_EMAIL_DOMAINS:
                        return email
            except Exception:
                continue
        return None

    async def discover_prospects(self, query):
        s=get_settings()
        if not s.WEB_DISCOVERY_ENABLED: return []
        terms=' '.join(query.get('keywords') or [query.get('industry','business'),'company',query.get('country','')])
        try:
            async with httpx.AsyncClient(timeout=20,headers={'User-Agent':s.PUBLIC_WEB_USER_AGENT}) as c:
                r=await c.get('https://html.duckduckgo.com/html/?q='+urllib.parse.quote(terms)); r.raise_for_status()
                soup=BeautifulSoup(r.text,'html.parser'); out=[]
                for a in soup.select('a.result__a')[:30]:
                    href=a.get('href',''); title=a.get_text(' ',strip=True); p=urllib.parse.urlparse(href)
                    if p.scheme not in ('http','https') or not p.netloc: continue
                    domain=p.netloc.lower().removeprefix('www.')
                    if any(x in domain for x in ('duckduckgo.com','facebook.com','linkedin.com','youtube.com','instagram.com')): continue
                    website=f'{p.scheme}://{p.netloc}'
                    email=await self._public_email(c, website)
                    out.append({'company_name':re.sub(r'\s+',' ',title)[:255],'website':website,'domain':domain,'contact_email':email,'country':query.get('country'),'industry':query.get('industry'),'description':title,'source':'web','source_id':domain,'source_url':href})
                return out
        except Exception as e: events.event('ERROR',component='web_discovery',error=str(e)); return []
