import httpx
from app.core.config import get_settings
from app.providers.base import ProspectProvider
from app.core.logging import events

class OSMProvider(ProspectProvider):
    name='osm'
    endpoints=['https://overpass-api.de/api/interpreter','https://overpass.private.coffee/api/interpreter','https://maps.mail.ru/osm/tools/overpass/api/interpreter']

    async def discover_prospects(self, query):
        s=get_settings()
        if not s.OSM_ENABLED:
            return []

        # OSM is useful for physical-business categories, not SaaS/startups.
        industry=str(query.get('industry','business')).lower().strip()
        tags={
            'real estate':['office=estate_agent','shop=estate_agent'],
            'consultant':['office=consulting'],
            'agency':['office=advertising_agency'],
            'education':['amenity=college','amenity=school'],
            'business':['office=*'],
        }
        if industry not in tags:
            return []

        parts=[]
        for tag in tags[industry]:
            k,v=tag.split('=',1)
            parts.append(f'node["{k}"{("="+repr(v)) if v!="*" else ""}](area.searchArea);')
        area=f'area["ISO3166-1"="{query.get("country_code","NG")}"]->.searchArea;' if query.get('country_code') else 'area["name"="Nigeria"]->.searchArea;'
        q='[out:json][timeout:25];'+area+'(' + ''.join(parts) + ');out center tags 60;'

        for endpoint in self.endpoints:
            try:
                async with httpx.AsyncClient(timeout=35,headers={'User-Agent':s.PUBLIC_WEB_USER_AGENT}) as c:
                    r=await c.post(endpoint,data=q)
                    r.raise_for_status()
                    elements=r.json().get('elements',[])
                out=[]
                for e in elements:
                    t=e.get('tags',{}); name=t.get('name')
                    if not name: continue
                    out.append({
                        'company_name':name,
                        'website':t.get('website') or t.get('contact:website'),
                        'contact_email':t.get('email') or t.get('contact:email'),
                        'contact_phone':t.get('phone') or t.get('contact:phone'),
                        'city':t.get('addr:city'),
                        'country':query.get('country','Nigeria'),
                        'industry':query.get('industry','business'),
                        'description':t.get('description'),
                        'source':'osm',
                        'source_id':str(e.get('id')),
                        'source_url':f'https://www.openstreetmap.org/{e.get("type","node")}/{e.get("id")}'
                    })
                return out
            except Exception as e:
                events.event('ERROR',component='osm',endpoint=endpoint,error=str(e))
        return []
