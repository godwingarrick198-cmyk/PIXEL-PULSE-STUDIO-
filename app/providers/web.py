import re, urllib.parse, httpx
from bs4 import BeautifulSoup
from app.core.config import get_settings
from app.providers.base import ProspectProvider
from app.core.logging import events

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
CONTACT_PATHS = ('/contact', '/contact-us', '/about', '/about-us', '/team', '/company')
BLOCKED_EMAIL_DOMAINS = {'example.com', 'example.org', 'example.net', 'sentry.io'}
SEARCH_ENGINES = (
    'https://www.google.com/search?q={q}',
    'https://www.bing.com/search?q={q}',
    'https://html.duckduckgo.com/html/?q={q}',
)
SOCIAL_DOMAINS = ('facebook.com','linkedin.com','youtube.com','instagram.com','twitter.com','x.com','tiktok.com')

class WebDiscoveryProvider(ProspectProvider):
    name='web'

    @staticmethod
    def _clean_email(value):
        email=(value or '').strip().lower().replace('mailto:','').split('?')[0]
        if EMAIL_RE.fullmatch(email) and email.split('@')[-1] not in BLOCKED_EMAIL_DOMAINS:
            return email
        return None

    @staticmethod
    def _clean_phone(value):
        value=re.sub(r'\s+',' ',(value or '').strip())
        return value if PHONE_RE.fullmatch(value) else None

    async def _public_contacts(self, client, website):
        if not website:
            return {}
        base=website.rstrip('/')
        best={}
        urls=[base]+[base+p for p in CONTACT_PATHS]
        for url in urls:
            try:
                r=await client.get(url, follow_redirects=True)
                if r.status_code >= 400:
                    continue
                final_url=str(r.url)
                soup=BeautifulSoup(r.text[:700000], 'html.parser')
                for a in soup.select('a[href^="mailto:"]'):
                    email=self._clean_email(a.get('href','')[7:])
                    if email:
                        best['contact_email']=email
                        best['public_contact_url']=final_url
                        break
                if not best.get('contact_email'):
                    for email in EMAIL_RE.findall(soup.get_text(' ', strip=True)):
                        email=self._clean_email(email)
                        if email:
                            best['contact_email']=email
                            best['public_contact_url']=final_url
                            break
                if not best.get('contact_phone'):
                    for a in soup.select('a[href^="tel:"]'):
                        phone=self._clean_phone(a.get('href','')[4:])
                        if phone:
                            best['contact_phone']=phone
                            break
                if not best.get('contact_phone'):
                    for phone in PHONE_RE.findall(soup.get_text(' ', strip=True)):
                        phone=self._clean_phone(phone)
                        if phone:
                            best['contact_phone']=phone
                            break
                for a in soup.select('a[href]'):
                    href=urllib.parse.urljoin(final_url,a.get('href',''))
                    if '/contact' in href.lower() or '/about' in href.lower() or '/team' in href.lower():
                        best.setdefault('public_contact_url',href)
                if best.get('contact_email'):
                    return best
            except Exception as e:
                events.event('WARNING', component='contact_enrichment', url=url, error=repr(e))
        return best

    async def enrich_items(self, items):
        """Free enrichment: visit public company websites and extract published contacts."""
        if not items:
            return items
        s=get_settings()
        headers={'User-Agent':s.PUBLIC_WEB_USER_AGENT or 'Mozilla/5.0 (Android 15) AppleWebKit/537.36 Chrome/128 Mobile Safari/537.36'}
        async with httpx.AsyncClient(timeout=15, headers=headers, follow_redirects=True) as client:
            for item in items:
                if item.get('contact_email'):
                    continue
                website=item.get('website')
                if not website:
                    continue
                contacts=await self._public_contacts(client,website)
                item.update({k:v for k,v in contacts.items() if v})
        return items

    def _result_links(self, html, engine):
        soup=BeautifulSoup(html,'html.parser'); links=[]
        selectors=soup.select('li.b_algo h2 a, li.b_algo a') if 'bing.com' in engine else soup.select('a.result__a') if 'duckduckgo.com' in engine else soup.select('a')
        for a in selectors:
            href=a.get('href',''); p=urllib.parse.urlparse(href)
            if p.scheme not in ('http','https') or not p.netloc:
                continue
            domain=p.netloc.lower().removeprefix('www.')
            if any(x in domain for x in ('google.com','bing.com','duckduckgo.com')+SOCIAL_DOMAINS):
                continue
            links.append((href,a.get_text(' ',strip=True)))
        return links

    async def discover_prospects(self, query):
        s=get_settings()
        if not s.WEB_DISCOVERY_ENABLED:
            return []
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
                            if domain in seen:
                                continue
                            seen.add(domain); website=f'{p.scheme}://{p.netloc}'
                            contacts=await self._public_contacts(c,website)
                            if not contacts.get('contact_email'):
                                continue
                            out.append({'company_name':re.sub(r'\s+',' ',title)[:255],'website':website,'domain':domain,'contact_email':contacts.get('contact_email'),'contact_phone':contacts.get('contact_phone'),'public_contact_url':contacts.get('public_contact_url'),'country':query.get('country'),'industry':query.get('industry'),'description':title,'source':'web','source_id':domain,'source_url':href})
                            if len(out)>=int(query.get('limit') or 10):
                                return out
                    except Exception as e:
                        errors.append(repr(e))
                if not out and errors:
                    events.event('ERROR',component='web_discovery',error='; '.join(errors[-3:]))
                return out
        except Exception as e:
            events.event('ERROR',component='web_discovery',error=repr(e)); return []
