import httpx
from app.core.config import get_settings
from app.providers.base import ProspectProvider
from app.core.logging import events


class OSMProvider(ProspectProvider):
    name = "osm"

    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.private.coffee/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    ]

    INDUSTRY_TAGS = {
        "restaurant": [("amenity", "restaurant"), ("amenity", "fast_food")],
        "cafe": [("amenity", "cafe")],
        "dental": [("amenity", "dentist")],
        "dentist": [("amenity", "dentist")],
        "school": [("amenity", "school")],
        "education": [("amenity", "school"), ("amenity", "college"), ("amenity", "university")],
        "college": [("amenity", "college")],
        "hotel": [("tourism", "hotel"), ("tourism", "guest_house")],
        "salon": [("shop", "beauty"), ("shop", "hairdresser")],
        "beauty": [("shop", "beauty"), ("shop", "hairdresser")],
        "pharmacy": [("amenity", "pharmacy")],
        "clinic": [("amenity", "clinic"), ("amenity", "doctors")],
        "hospital": [("amenity", "hospital")],
        "car repair": [("shop", "car_repair")],
        "auto repair": [("shop", "car_repair")],
        "real estate": [("office", "estate_agent")],
        "estate agent": [("office", "estate_agent")],
        "consultant": [("office", "consulting")],
        "consulting": [("office", "consulting")],
        "agency": [("office", "advertising_agency")],
        "marketing agency": [("office", "advertising_agency")],
        "lawyer": [("office", "lawyer")],
        "accountant": [("office", "accountant")],
        "business": [("office", "*")],
        "company": [("office", "*")],
    }

    COUNTRY_CODES = {
        "nigeria": "NG",
        "united states": "US",
        "usa": "US",
        "united kingdom": "GB",
        "uk": "GB",
        "canada": "CA",
        "australia": "AU",
        "south africa": "ZA",
        "ghana": "GH",
        "kenya": "KE",
        "united arab emirates": "AE",
        "uae": "AE",
        "saudi arabia": "SA",
    }

    async def discover_prospects(self, query):
        settings = get_settings()
        if not settings.OSM_ENABLED:
            return []

        industry = str(query.get("industry") or "business").strip().lower()
        country = str(query.get("country") or "Nigeria").strip()
        tags = self.INDUSTRY_TAGS.get(industry)

        # OSM is intentionally used for physical/local businesses.
        # Web discovery remains a secondary enrichment source.
        if not tags:
            return []

        country_code = str(query.get("country_code") or "").strip().upper()
        if not country_code:
            country_code = self.COUNTRY_CODES.get(country.lower(), "")

        if country_code:
            area = f'area["ISO3166-1"="{country_code}"]->.searchArea;'
        else:
            safe_country = country.replace('"', "")
            area = f'area["name"="{safe_country}"]->.searchArea;'

        parts = []
        for key, value in tags:
            value_filter = "" if value == "*" else f'="{value}"'
            parts.append(f'nwr["{key}"{value_filter}](area.searchArea);')

        query_text = (
            "[out:json][timeout:30];"
            + area
            + "("
            + "".join(parts)
            + ");"
            + "out center;"
        )

        for endpoint in self.endpoints:
            try:
                async with httpx.AsyncClient(
                    timeout=40,
                    headers={"User-Agent": settings.PUBLIC_WEB_USER_AGENT},
                ) as client:
                    response = await client.post(endpoint, data=query_text)
                    response.raise_for_status()
                    elements = response.json().get("elements", [])

                results = []
                seen = set()

                for element in elements:
                    tags_data = element.get("tags") or {}
                    name = (tags_data.get("name") or "").strip()
                    if not name:
                        continue

                    source_id = f'{element.get("type", "element")}:{element.get("id")}'
                    if source_id in seen:
                        continue
                    seen.add(source_id)

                    results.append(
                        {
                            "company_name": name,
                            "website": (
                                tags_data.get("website")
                                or tags_data.get("contact:website")
                                or tags_data.get("url")
                            ),
                            "contact_email": (
                                tags_data.get("email")
                                or tags_data.get("contact:email")
                            ),
                            "contact_phone": (
                                tags_data.get("phone")
                                or tags_data.get("contact:phone")
                                or tags_data.get("contact:mobile")
                            ),
                            "city": (
                                tags_data.get("addr:city")
                                or tags_data.get("addr:town")
                                or tags_data.get("addr:suburb")
                            ),
                            "country": country,
                            "industry": query.get("industry") or industry,
                            "description": tags_data.get("description"),
                            "source": "osm",
                            "source_id": source_id,
                            "source_url": (
                                f'https://www.openstreetmap.org/'
                                f'{element.get("type", "node")}/{element.get("id")}'
                            ),
                        }
                    )

                    if len(results) >= max(20, int(query.get("limit") or 10) * 10):
                        break

                events.event(
                    "PROSPECT_PROVIDER_RESULT",
                    provider=self.name,
                    industry=industry,
                    country=country,
                    count=len(results),
                )
                return results

            except Exception as exc:
                events.event(
                    "ERROR",
                    component="osm",
                    endpoint=endpoint,
                    industry=industry,
                    country=country,
                    error=repr(exc),
                )

        return []
