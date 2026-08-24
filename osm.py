import httpx
from app.core.config import get_settings
from app.providers.base import ProspectProvider
from app.core.logging import events

class OSMProvider(ProspectProvider):
    name='osm'
    endpoints=['https://overpass-api.de/api/interpreter','https://overpass.private.coffee/api/interpreter','https://maps.mail.ru/osm/tools/overpass/api/interpreter']
    async def discover_prospects(self, query):
        s=get_settings()
        if not s.OSM_ENABLED: return []
        tags={'real estate':['office=estate_agent','shop=estate_agent'],'consultant':['office=consulting'],'agency':['office=advertising_agency'],'hotel':['tourism=hotel'],'education':['amenity=college','amenity=school'],'business':['office=*']}
        selected=tags.get(query.get('industry','').lower(),tags['business'])
        parts=[]
        for tag in selected:
            k,v=tag.split('=',1); parts.append(f'node["{k}"{("="+repr(v)) if v!="*" else ""}](area.searchArea);')
        # A broad query is intentionally bounded by country/area when supplied.
        area=f'area["ISO3166-1"="{query.get("country_code","NG")}"]->.searchArea;' if query.get('country_code') else 'area["name"="Nigeria"]->.searchArea;'
        q='[out:json][timeout:25];'+area+'(' + ''.join(parts) + ');out center tags 60;'
        for endpoint in self.endpoints:
            try:
                async with httpx.AsyncClient(timeout=35,headers={'User-Agent':s.PUBLIC_WEB_USER_AGENT}) as c:
                    r=await c.post(endpoint,data=q); r.raise_for_status(); elements=r.json().get('elements',[])
                out=[]
                for e in elements:
                    t=e.get('tags',{}); name=t.get('name');
                    if not name: continue
                    website=t.get('website') or t.get('contact:website'); email=t.get('email') or t.get('contact:email')
                    out.append({'company_name':name,'website':website,'contact_email':email,'contact_phone':t.get('phone') or t.get('contact:phone'),'city':t.get('addr:city'),'country':query.get('country','Nigeria'),'industry':query.get('industry','business'),'description':t.get('description'),'source':'osm','source_id':str(e.get('id')),'source_url':f'https://www.openstreetmap.org/{e.get("type","node")}/{e.get("id")}'} )
                return out
            except Exception as e: events.event('ERROR',component='osm',endpoint=endpoint,error=str(e))
        return []
