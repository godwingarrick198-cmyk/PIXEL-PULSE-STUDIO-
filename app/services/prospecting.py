import re
from urllib.parse import urlparse, urljoin

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select, or_, func

from app.models.entities import Prospect, SuppressionList
from app.providers import ApolloProvider, OSMProvider, WebDiscoveryProvider, ProductHuntProvider
from app.services.ai import AIService
from app.core.config import get_settings
from app.core.logging import events


EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
SOCIAL_HOSTS = {
    "facebook.com",
    "linkedin.com",
    "instagram.com",
    "youtube.com",
    "x.com",
    "twitter.com",
}


class ProspectingService:
    def __init__(self):
        self.s = get_settings()
        self.ai = AIService()
        self.providers = []

        # Free sources only. OSM is the primary physical-business source;
        # web discovery is the secondary source/enrichment layer.
        if self.s.OSM_ENABLED:
            self.providers.append(OSMProvider())
        if self.s.WEB_DISCOVERY_ENABLED:
            self.providers.append(WebDiscoveryProvider())
        if self.s.PRODUCT_HUNT_ENABLED:
            self.providers.append(ProductHuntProvider())
        if self.s.APOLLO_ENABLED and self.s.APOLLO_API_KEY:
            self.providers.append(ApolloProvider())

    def normalize_domain(self, url):
        if not url:
            return None
        try:
            parsed = urlparse(url if "://" in url else "https://" + url)
            return parsed.netloc.lower().removeprefix("www.").split(":")[0] or None
        except Exception:
            return None

    def suppressed(self, db, prospect):
        domain = self.normalize_domain(
            prospect.get("website") or prospect.get("domain")
        )
        email = (prospect.get("contact_email") or "").strip().lower()
        company = (prospect.get("company_name") or "").strip()

        checks = []
        if email:
            checks.append(SuppressionList.email == email)
        if domain:
            checks.append(SuppressionList.domain == domain)
        if company:
            checks.append(SuppressionList.company.ilike(company))

        return bool(
            checks
            and db.scalar(select(SuppressionList.id).where(or_(*checks)))
        )

    async def _enrich_public_contact(self, raw):
        website = raw.get("website")
        email = (raw.get("contact_email") or "").strip().lower()

        settings = self.s
        name = (raw.get("company_name") or "").strip()
        country = (raw.get("country") or "").strip()

        headers = {
            "User-Agent": settings.PUBLIC_WEB_USER_AGENT
            or "PixelPulseStudio/1.0"
        }

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(12.0),
                headers=headers,
                follow_redirects=True,
            ) as client:
                # If OSM gives a business name but no website, use public web
                # search to locate the business's official site.
                if not website and name and settings.WEB_DISCOVERY_ENABLED:
                    search = await client.get(
                        "https://html.duckduckgo.com/html/",
                        params={"q": f'"{name}" {country} official website'},
                    )

                    if search.is_success:
                        soup = BeautifulSoup(search.text, "html.parser")
                        for link in soup.select("a[href]"):
                            href = link.get("href", "")
                            parsed = urlparse(href)
                            domain = (
                                parsed.netloc.lower()
                                .removeprefix("www.")
                            )

                            if (
                                parsed.scheme in ("http", "https")
                                and domain
                                and not any(
                                    domain == blocked
                                    or domain.endswith("." + blocked)
                                    for blocked in SOCIAL_HOSTS
                                )
                            ):
                                website = f"{parsed.scheme}://{parsed.netloc}"
                                break

                if not website:
                    return raw

                raw["website"] = website
                raw["domain"] = self.normalize_domain(website)

                base = website.rstrip("/")
                candidates = [
                    website,
                    *[
                        urljoin(base, path)
                        for path in (
                            "/contact",
                            "/contact-us",
                            "/about",
                            "/about-us",
                            "/team",
                            "/company",
                        )
                    ],
                ]

                for url in candidates:
                    try:
                        response = await client.get(url)
                        if not response.is_success:
                            continue

                        soup = BeautifulSoup(
                            response.text[:700000],
                            "html.parser",
                        )

                        found = [
                            link.get("href", "")[7:].split("?")[0]
                            for link in soup.select('a[href^="mailto:"]')
                        ]
                        found += EMAIL_RE.findall(
                            soup.get_text(" ", strip=True)
                        )

                        for candidate in found:
                            candidate = (
                                candidate.strip()
                                .lower()
                                .strip(".,;:()[]<>")
                            )

                            if (
                                EMAIL_RE.fullmatch(candidate)
                                and candidate.split("@")[-1]
                                not in {
                                    "example.com",
                                    "example.org",
                                    "example.net",
                                }
                            ):
                                raw["contact_email"] = candidate
                                raw["public_contact_url"] = url
                                return raw

                    except Exception:
                        continue

        except Exception as exc:
            events.event(
                "ERROR",
                component="public_contact_enrichment",
                error=repr(exc),
            )

        if website:
            raw["website"] = website
            raw["domain"] = self.normalize_domain(website)
            return await self._research_website(raw)

        return raw

    async def _research_website(self, raw):
        website = raw.get("website")
        if not website:
            return raw
        headers = {"User-Agent": self.s.PUBLIC_WEB_USER_AGENT or "PixelPulseStudio/1.0"}
        base = website.rstrip("/")
        paths = ["/", "/about", "/about-us", "/services", "/products", "/solutions", "/news", "/blog", "/events"]
        chunks = []
        try:
            async with httpx.AsyncClient(timeout=10, headers=headers, follow_redirects=True) as client:
                for path in paths:
                    try:
                        response = await client.get(base + path)
                        if not response.is_success:
                            continue
                        soup = BeautifulSoup(response.text[:500000], "html.parser")
                        for tag in soup(["script", "style", "noscript"]):
                            tag.decompose()
                        text = soup.get_text(" ", strip=True)
                        if text:
                            chunks.append(text[:3500])
                        if len(" ".join(chunks)) >= 14000:
                            break
                    except Exception:
                        continue
        except Exception as exc:
            events.event("ERROR", component="website_research", error=repr(exc))
        if chunks:
            raw["research_text"] = " ".join(chunks)[:14000]
        return raw

    async def discover(self, db, query, limit):
        if limit <= 0 or not self.providers:
            return []

        # Collect from both free discovery layers. Do not stop just because
        # OSM returned many raw records: most OSM records do not contain email,
        # so the web provider must still get a chance to contribute candidates.
        all_items = []

        for provider in self.providers:
            try:
                items = await provider.discover_prospects(query)
                all_items.extend(items or [])
                events.event(
                    "PROSPECT_PROVIDER_RESULT",
                    provider=provider.name,
                    count=len(items or []),
                )
            except Exception as exc:
                events.event(
                    "ERROR",
                    component="provider",
                    provider=provider.name,
                    error=repr(exc),
                )

        # Prefer records that already have an email/website before spending
        # network time on public-contact enrichment.
        all_items.sort(
            key=lambda item: (
                bool(item.get("contact_email")),
                bool(item.get("website")),
                bool(item.get("contact_phone")),
            ),
            reverse=True,
        )

        # Avoid huge enrichment runs while still giving the free providers
        # enough candidates to find at least the requested number.
        max_candidates = max(20, limit * 10)
        all_items = all_items[:max_candidates]

        saved = []
        seen = set()
        stats = {"raw": len(all_items), "no_name": 0, "no_email": 0, "duplicate": 0, "suppressed": 0, "not_qualified": 0, "no_opportunity": 0, "saved": 0}

        for raw in all_items:
            raw = await self._enrich_public_contact(dict(raw))

            domain = self.normalize_domain(
                raw.get("website") or raw.get("domain")
            )
            email = (raw.get("contact_email") or "").strip().lower()
            name = (raw.get("company_name") or "").strip()

            if not name:
                stats["no_name"] += 1
                continue

            if not email or not EMAIL_RE.fullmatch(email):
                stats["no_email"] += 1
                continue

            key = email or domain or name.lower()
            if key in seen:
                stats["duplicate"] += 1
                continue
            seen.add(key)

            checks = [Prospect.contact_email == email]
            if domain:
                checks.append(Prospect.domain == domain)
            if name:
                checks.append(
                    func.lower(Prospect.company_name) == name.lower()
                )

            if db.scalar(select(Prospect).where(or_(*checks))):
                stats["duplicate"] += 1
                continue

            if self.suppressed(db, raw):
                stats["suppressed"] += 1
                continue

            qualification = self.ai.qualify(
                {
                    **raw,
                    "domain": domain,
                    "contact_email": email,
                }
            )

            if (not qualification.qualified or qualification.score < self.s.MIN_QUALIFICATION_SCORE or qualification.recommended_service == "SKIP"):
                stats["not_qualified"] += 1
                continue

            if qualification.presentation_opportunity_score < 60:
                stats["no_opportunity"] += 1
                continue

            prospect = Prospect(
                company_name=name,
                website=raw.get("website"),
                domain=domain,
                industry=raw.get("industry") or qualification.company_type,
                description=raw.get("description"),
                country=raw.get("country"),
                city=raw.get("city"),
                founder_name=raw.get("founder_name"),
                contact_name=raw.get("contact_name"),
                contact_email=email,
                contact_phone=raw.get("contact_phone"),
                public_contact_url=raw.get("public_contact_url"),
                linkedin_url=raw.get("linkedin_url"),
                source=raw.get("source"),
                source_id=str(raw.get("source_id") or ""),
                source_url=raw.get("source_url"),
                service_match=qualification.recommended_service,
                qualification_score=qualification.score,
                estimated_budget=qualification.estimated_budget,
                purchase_likelihood=qualification.purchase_likelihood,
                status="QUALIFIED",
                qualification_json=qualification.model_dump(),
            )

            db.add(prospect)
            db.flush()
            saved.append(prospect)
            stats["saved"] += 1

            events.event(
                "PROSPECT_QUALIFIED",
                prospect_id=prospect.id,
                score=qualification.score,
            )

            if len(saved) >= limit:
                break

        db.commit()

        events.event(
            "PROSPECT_DISCOVERY_SUMMARY",
            requested=limit,
            **stats,
        )

        return saved
