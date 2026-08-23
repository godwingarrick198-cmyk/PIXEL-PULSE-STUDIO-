import re, urllib.parse
import httpx
from bs4 import BeautifulSoup
from app.core.config import get_settings
from app.providers.base import ProspectProvider
from app.core.logging import events

class WebDiscoveryProvider(ProspectProvider):
    name='web'
    async def discover_prospects(self, query):
        s=get_settings()
        if not s.WEB_DISCOVERY_ENABLED: return []
        terms=' '.join(query.get('keywords') or [query.get('industry','business'), 'company', query.get('country','')])
        url='https://html.duckduckgo.com/html/?q='+urllib.parse.quote(terms)
        try:
            async with httpx.AsyncClient(timeout=25,headers={'User-Agent':s.PUBLIC_WEB_USER_AGENT}) as c:
                r=await c.get(url); r.raise_for_status()
            soup=BeautifulSoup(r.text,'html.parser'); out=[]
            for a in soup.select('a.result__a')[:30]:
                href=a.get('href',''); title=a.get_text(' ',strip=True); parsed=urllib.parse.urlparse(href)
                if parsed.scheme not in ('http','https') or not parsed.netloc: continue
                domain=parsed.netloc.lower().removeprefix('www.')
                if any(x in domain for x in ('duckduckgo.com','facebook.com','linkedin.com','youtube.com','instagram.com')): continue
                out.append({'company_name':re.sub(r'\s+',' ',title)[:255],'website':f'{parsed.scheme}://{parsed.netloc}','domain':domain,'country':query.get('country'),'industry':query.get('industry'),'description':title,'source':'web','source_id':domain,'source_url':href})
            return out
        except Exception as e: events.event('ERROR',component='web_discovery',error=str(e)); return []
