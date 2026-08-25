class BaseProvider:
    name = "base"

    async def discover_prospects(self, query):
        return []


class WebDiscoveryProvider(BaseProvider):
    name = "web"

class OSMProvider(BaseProvider):
    name = "osm"

class ProductHuntProvider(BaseProvider):
    name = "producthunt"
