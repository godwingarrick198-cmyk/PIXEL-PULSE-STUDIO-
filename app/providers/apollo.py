import httpx
from app.core.config import get_settings
from app.providers.base import ProspectProvider
from app.core.logging import events

class ApolloProvider(ProspectProvider):
    """Optional Apollo-backed company/contact discovery and enrichment.

    Apollo is only used when APOLLO_ENABLED=true and APOLLO_API_KEY is set.
    Search finds companies/decision makers; enrichment supplies a usable email
    when Apollo has one. No email is invented or guessed.
    """
    name = 'apollo'
    base_url = 'https://api.apollo.io/api/v1'

    async def discover_prospects(self, query):
        s = get_settings()
        if not (s.APOLLO_ENABLED and s.APOLLO_API_KEY):
            return []

        industry = str(query.get('industry') or '').strip()
        country = str(query.get('country') or '').strip()
        limit = min(int(query.get('limit') or 10), 20)
        headers = {
            'accept': 'application/json',
            'content-type': 'application/json',
            'x-api-key': s.APOLLO_API_KEY,
            'Cache-Control': 'no-cache',
        }

        try:
            async with httpx.AsyncClient(timeout=25, headers=headers) as client:
                # Organization search costs Apollo credits, so keep this small.
                org_payload = {
                    'q_organization_keyword_tags': [industry] if industry else [],
                    'organization_locations': [country] if country else [],
                    'per_page': min(limit, 10),
                    'page': 1,
                }
                org_resp = await client.post(
                    f'{self.base_url}/mixed_companies/search', json=org_payload
                )
                org_resp.raise_for_status()
                orgs = org_resp.json().get('organizations', [])

                out = []
                for org in orgs:
                    if len(out) >= limit:
                        break
                    domain = (org.get('primary_domain') or org.get('domain') or '').strip().lower()
                    if not domain:
                        continue

                    # People search itself does not expose email addresses, so
                    # enrich a small number of senior decision makers by domain.
                    people_payload = {
                        'q_organization_domains_list': [domain],
                        'person_seniorities': ['owner', 'founder', 'c_suite', 'partner', 'vp', 'head'],
                        'contact_email_status': ['verified'],
                        'per_page': 3,
                        'page': 1,
                    }
                    people_resp = await client.post(
                        f'{self.base_url}/mixed_people/api_search', json=people_payload
                    )
                    people_resp.raise_for_status()
                    people = people_resp.json().get('people', [])

                    for person in people:
                        if len(out) >= limit:
                            break
                        person_id = person.get('id')
                        if not person_id:
                            continue
                        enrich_resp = await client.post(
                            f'{self.base_url}/people/match',
                            params={'reveal_personal_emails': 'false'},
                            json={
                                'id': person_id,
                                'reveal_personal_emails': False,
                            },
                        )
                        if not enrich_resp.is_success:
                            continue
                        match = enrich_resp.json().get('person') or {}
                        email = (match.get('email') or '').strip().lower()
                        if not email or email.startswith('[email'):
                            continue

                        org_data = match.get('organization') or org
                        out.append({
                            'company_name': org_data.get('name') or org.get('name'),
                            'website': org_data.get('website_url') or f'https://{domain}',
                            'domain': domain,
                            'industry': industry or org_data.get('industry'),
                            'country': country,
                            'description': org_data.get('short_description') or org.get('short_description'),
                            'founder_name': match.get('name'),
                            'contact_name': match.get('name'),
                            'contact_email': email,
                            'contact_phone': match.get('phone_number'),
                            'linkedin_url': match.get('linkedin_url'),
                            'source': 'apollo',
                            'source_id': str(person_id),
                            'source_url': f'https://app.apollo.io/#/people/{person_id}',
                        })
                return out
        except Exception as e:
            events.event('ERROR', component='apollo', error=repr(e))
            return []
