import re, urllib.parse, httpx
from bs4 import BeautifulSoup
from app.core.config import get_settings
from app.providers.base import ProspectProvider
from app.core.logging import events

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
CONTACT_PATHS = ('/contact', '/contact-us', '/about', '/about-us', '/team')
BLOCKED_EMAIL_DOMAINS = {'example.com', 'example.org', 'example.net'}
SEARCH_ENGINES = ('https://www.google.com/search?q={q}', 'https://www.bing.com/search?q={q}', 'https://html.duckduckgo.com/html/?q={q}')

class WebDiscoveryProvider(ProspectProvider):
    name='web'

    async def _public_email(self, client, website):
        base = website.rstrip('/')
        for url in [base] + [base + p for p in CONTACT_PATHS]:
            try:
                r = await client.get(url, follow_redirects=True)
                if r.status_code >= 400: continue
                soup = BeautifulSoup(r.text[:500000], 'html.parser')
                for a in soup.select('a[href^="mailto:"]'):
                    email = a.get('href','')[7:].split('?')[0].strip().lower()
                    if EMAIL_RE.fullmatch(email) and email.split('@')[-1] not in BLOCKED_EMAIL_DOMAINS: return email
                for email in EMAIL_RE.findall(soup.get_text(' ', strip=True)):
                    email = email.lower()
                    if email.split('@')[-1] not in BLOCKED_EMAIL_DOMAINS: return email
            except Exception as e:
                events.event('WARNING', component='email_enrichment', url=url, error=repr(e))
        return None

    def _result_links(self, html, engine):
        soup = BeautifulSoup(html, 'html.parser'); links=[]
        selectors = soup.select('li.b_algo h2 a, li.b_algo a') if 'bing.com' in engine else soup.select('a.result__a') if 'duckduckgo.com' in engine else soup.select('a')
        for a in selectors:
            href=a.get('href',''); p=urllib.parse.urlparse(href)
            if p.scheme not in ('http','https') or not p.netloc: continue
            domain=p.netloc.lower().removeprefix('www.')
            if any(x in domain for x in ('google.com','bing.com','duckduckgo.com','facebook.com','linkedin.com','youtube.com','instagram.com','twitter.com','x.com')): continue
            links.append((href,a.get_text(' ',strip=True)))
        return links

    async def discover_prospects(self, query):
        s=get_settings()
        if not s.WEB_DISCOVERY_ENABLED: return []
        terms=' '.join(query.get('keywords') or [query.get('industry','business'),'company',query.get('country','')])
        headers={'User-Agent':s.PUBLIC_WEB_USER_AGENT or 'Mozilla/5.0 (Android 15) AppleWebKit/537.36 Chrome/128 Mobile Safari/537.36'}
        out=[]; seen=set(); errors=[]
        try:
            async with httpx.AsyncClient(timeout=25,headers=headers,follow_redirects=True) as c:
                for template in SEARCH_ENGINES:
                    try:
                        r=await c.get(template.format(q=urllib.parse.quote_plus(terms))); r.raise_for_status()
                        for href,title in self._result_links(r.text,template):
                            p=urllib.parse.urlparse(href); domain=p.netloc.lower().removeprefix('www.')
                            if domain in seen: continue
                            seen.add(domain); website=f'{p.scheme}://{p.netloc}'
                            email=await self._public_email(c,website)
                            if not email: continue
                            out.append({'company_name':re.sub(r'\s+',' ',title)[:255],'website':website,'domain':domain,'contact_email':email,'country':query.get('country'),'industry':query.get('industry'),'description':title,'source':'web','source_id':domain,'source_url':href})
                            if len(out)>=int(query.get('limit') or 10): return out
                    except Exception as e: errors.append(repr(e))
                if not out and errors: events.event('ERROR',component='web_discovery',error='; '.join(errors[-3:]))
                return out
        except Exception as e:
            events.event('ERROR',component='web_discovery',error=repr(e)); return []
