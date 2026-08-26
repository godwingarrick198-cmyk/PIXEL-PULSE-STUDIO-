import httpx
from app.core.config import get_settings
from app.providers.base import ProspectProvider
from app.core.logging import events

class ProductHuntProvider(ProspectProvider):
    name='product_hunt'
    endpoint='https://api.producthunt.com/v2/api/graphql'
    query='''query($first:Int!){posts(first:$first){edges{node{id name tagline website{url} url user{name}}}}}'''
    async def discover_prospects(self, query):
        s=get_settings()
        if not (s.PRODUCT_HUNT_ENABLED and s.PRODUCT_HUNT_ACCESS_TOKEN and s.PRODUCT_HUNT_COMMERCIAL_APPROVED): return []
        try:
            async with httpx.AsyncClient(timeout=25) as c:
                r=await c.post(self.endpoint,json={'query':self.query,'variables':{'first':30}},headers={'Authorization':f'Bearer {s.PRODUCT_HUNT_ACCESS_TOKEN}'}); r.raise_for_status()
            edges=r.json().get('data',{}).get('posts',{}).get('edges',[])
            return [{'company_name':e['node']['name'],'website':(e['node'].get('website') or {}).get('url'),'description':e['node'].get('tagline'),'founder_name':(e['node'].get('user') or {}).get('name'),'source':'product_hunt','source_id':e['node']['id'],'source_url':e['node'].get('url'),'industry':query.get('industry','startup')} for e in edges]
        except Exception as e: events.event('ERROR',component='product_hunt',error=str(e)); return []
