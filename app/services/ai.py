import json
from pydantic import BaseModel, Field
from app.core.config import get_settings
from app.core.logging import events

GEMINI_MODEL = 'gemini-3.6-flash'

SERVICES = {
    'startup': 'Investor Pitch Deck',
    'saas': 'Investor/Sales Deck',
    'technology company': 'Investor/Sales Deck',
    'marketing agency': 'Client Sales Deck',
    'agency': 'Client Sales Deck',
    'consultant': 'Proposal Deck',
    'consulting': 'Proposal Deck',
    'real estate': 'Property/Investment Presentation',
    'property': 'Property/Investment Presentation',
    'corporate': 'Corporate Presentation',
    'business': 'Corporate Presentation',
    'restaurant': 'Business/Company Presentation',
    'cafe': 'Business/Company Presentation',
    'dental': 'Business/Company Presentation',
    'dentist': 'Business/Company Presentation',
    'school': 'Education/Training Presentation',
    'education': 'Education/Training Presentation',
    'college': 'Education/Training Presentation',
    'university': 'Education/Training Presentation',
    'hotel': 'Business/Company Presentation',
    'salon': 'Business/Company Presentation',
    'beauty': 'Business/Company Presentation',
    'clinic': 'Business/Company Presentation',
    'hospital': 'Business/Company Presentation',
    'pharmacy': 'Business/Company Presentation',
    'lawyer': 'Business/Company Presentation',
    'accountant': 'Business/Company Presentation',
    'car repair': 'Business/Company Presentation',
    'auto repair': 'Business/Company Presentation',
    'coach': 'Webinar/Training Presentation',
    'e-commerce': 'Product Presentation',
    'product': 'Product Presentation',
    'webinar': 'Webinar Presentation',
    'training': 'Training Presentation',
}

PACKAGES = {
    'STARTER': (10, 250),
    'PROFESSIONAL': (20, 500),
    'PREMIUM': (30, 1000),
}


class Qualification(BaseModel):
    qualified: bool
    score: int = Field(ge=0, le=100)
    company_type: str
    recommended_service: str
    estimated_budget: float
    purchase_likelihood: float = Field(ge=0, le=1)
    reason: str
    personalization_points: list[str] = []
    recommended_channel: str = 'email'
    presentation_opportunity_score: int = Field(default=0, ge=0, le=100)
    opportunity_type: str = 'General business presentation'
    opportunity_evidence: list[str] = []
    outreach_angle: str = ''


class ReplyAnalysis(BaseModel):
    interested: bool
    urgency: str = 'normal'
    summary: str
    recommended_action: str
    reply: str
    requested_slide_count: int | None = Field(default=None, ge=1, le=200)
    presentation_idea: str = ''


class AIService:
    def __init__(self):
        self.settings = get_settings()
        self.client = None
        if self.settings.GEMINI_API_KEY:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.settings.GEMINI_API_KEY)
            except Exception as e:
                events.event('ERROR', component='gemini_init', error=str(e))

    def _fallback(self, prospect):
        text = ' '.join(
            str(prospect.get(k) or '')
            for k in ('company_name', 'industry', 'description', 'research_text')
        ).lower()

        service = next((v for k, v in SERVICES.items() if k in text), None)
        if not service:
            return Qualification(
                qualified=False,
                score=0,
                company_type='unknown',
                recommended_service='SKIP',
                estimated_budget=0,
                purchase_likelihood=0,
                reason='No configured presentation service match.',
            )

        signals = {
            'launch': ('launch', 'new service', 'new product', 'new branch', 'opening'),
            'growth': ('expansion', 'growing', 'growth', 'locations', 'branches'),
            'sales': ('services', 'solutions', 'portfolio', 'packages', 'products'),
            'event': ('event', 'conference', 'webinar', 'training', 'workshop'),
            'partnership': ('partner', 'partnership', 'investor', 'funding', 'sponsor'),
            'weak_material': ('about us', 'our services', 'contact us'),
        }

        evidence = []
        opportunity_type = 'Business/company presentation'
        for label, words in signals.items():
            if any(word in text for word in words):
                evidence.append(f'Public business information contains {label} signals.')
        if 'launch' in text:
            opportunity_type = 'Launch/product presentation'
        elif 'investor' in text or 'funding' in text:
            opportunity_type = 'Investor/pitch presentation'
        elif 'event' in text or 'webinar' in text or 'training' in text:
            opportunity_type = 'Event/training presentation'
        elif 'services' in text or 'solutions' in text:
            opportunity_type = 'Sales/company presentation'

        score = 72 if evidence else 60
        reason = (
            'Public business information shows a presentation-relevant use case.'
            if evidence
            else 'Business type matches a presentation service, but public evidence is limited.'
        )
        return Qualification(
            qualified=True,
            score=score,
            company_type=prospect.get('industry') or 'business',
            recommended_service=service,
            estimated_budget=500,
            purchase_likelihood=.55,
            reason=reason,
            personalization_points=evidence[:5] or [prospect.get('company_name', '')],
            recommended_channel='email',
            presentation_opportunity_score=score,
            opportunity_type=opportunity_type,
            opportunity_evidence=evidence[:5],
            outreach_angle=(
                evidence[0]
                if evidence
                else 'Offer presentation support based on the company\'s public business information.'
            ),
        )

    def qualify(self, prospect):
        if not self.client:
            return self._fallback(prospect)

        prompt = f'''
You are the prospect-research and sales-qualification agent for Pixel Pulse Studio.

Goal: find real businesses that have a credible reason to need a presentation service, not merely businesses that exist.

Use ONLY the supplied public information. Never invent facts.

Analyze:
1. What the company does.
2. What it is currently promoting, selling, launching, expanding, teaching, pitching, or presenting.
3. Whether a presentation could reasonably help that specific situation.
4. Concrete evidence from the supplied information.
5. A truthful outreach angle based on that evidence.

Strong opportunity signals include launches, new products/services, expansion, multiple services that need a company/sales deck, investor/funding activity, partnerships, B2B sales, events, webinars, training, proposals, property/investment offerings, or other situations where a presentation is a plausible business need.

Do NOT qualify a company only because its industry is "restaurant", "school", "salon", etc. There must be a credible presentation use case or enough public evidence to justify outreach.

Prospect data:
{json.dumps(prospect, default=str)}

Return JSON with:
qualified,
score 0-100,
company_type,
recommended_service,
estimated_budget,
purchase_likelihood 0-1,
reason,
personalization_points,
recommended_channel,
presentation_opportunity_score 0-100,
opportunity_type,
opportunity_evidence,
outreach_angle.
'''

        try:
            resp = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config={
                    'response_mime_type': 'application/json',
                    'response_schema': Qualification.model_json_schema(),
                },
            )
            return Qualification.model_validate(json.loads(resp.text))
        except Exception as e:
            events.event('ERROR', component='gemini_qualification', error=str(e))
            return self._fallback(prospect)

    def generate_outreach(self, prospect, service):
        name = prospect.get('contact_name') or prospect.get('founder_name') or 'there'
        company = prospect.get('company_name') or 'your company'
        q = prospect.get('qualification_json') or {}
        evidence = q.get('opportunity_evidence') or q.get('personalization_points') or []
        angle = q.get('outreach_angle') or ''
        evidence_line = evidence[0] if evidence else 'your current business activity'
        subject = f'Presentation idea for {company}'

        body = (
            f'Hi {name},\n\n'
            f'I came across {company} and noticed {evidence_line.lower() if evidence_line else "your current business activity"}. '
            f'That looks like a situation where a clear, professional presentation could help.\n\n'
            f'Pixel Pulse Studio creates professional {service.lower()}s tailored to the specific business goal. '
            f'{angle} Would you be open to discussing a presentation around this?\n\n'
            f'If yes, I would like to understand exactly what you need so I can shape the right deck. '
            f'What is the presentation for, roughly how many slides would you like, and what main idea or message do you want the presentation to communicate? '
            f'Who is the intended audience, if you already know?\n\n'
            f'Best,\n'
            f'Pixel Pulse Studio'
        )
        return subject, body

    def analyze_reply(self, prospect, conversation):
        if not self.client:
            text = conversation.lower()
            interested = any(
                x in text
                for x in (
                    'interested', 'yes', 'tell me more', 'pricing', 'price',
                    'cost', 'package', 'quote', "let's talk", 'lets talk',
                    'available', 'how much', 'need a presentation',
                )
            )
            import re
            slide_match = re.search(r'(?:\b|about\s*)(\d{1,3})\s*(?:slides?|pages?)\b', text)
            idea = ''
            for marker in ('for ', 'about ', 'to present '):
                if marker in conversation.lower():
                    idea = conversation.strip()[:300]
                    break
            return ReplyAnalysis(
                interested=interested,
                urgency='high' if interested else 'normal',
                summary='Potentially interested reply.' if interested else 'General reply.',
                recommended_action='Notify owner and stop automated sales replies.' if interested else 'Continue conversation with a short helpful reply.',
                reply='Thanks for getting back to us. Garrick from Pixel Pulse Studio will follow up with you directly on the details and next steps.' if interested else 'Thanks for getting back to us. I can share the relevant details and next steps.',
                requested_slide_count=int(slide_match.group(1)) if slide_match else None,
                presentation_idea=idea,
            )

        prompt = f'''
You are the sales qualification agent for Pixel Pulse Studio.

Analyze the latest prospect email in context. Never invent facts.

Set interested=true when the prospect shows buying interest, asks for pricing/quote/availability/package details, asks to discuss the project, or clearly wants to proceed.

Also extract project requirements when the prospect provides them:
- requested_slide_count: a number of slides/pages if stated, otherwise null.
- presentation_idea: the actual presentation topic, purpose, or main idea if stated, otherwise an empty string.

When interested=true, recommend notifying the owner and stopping automated sales replies.
Otherwise provide a short professional reply that asks for missing project details without inventing pricing or capabilities.

Prospect:
{json.dumps(prospect, default=str)}

Conversation:
{conversation}

Return JSON with interested, urgency, summary, recommended_action, reply, requested_slide_count, presentation_idea.
'''

        try:
            resp = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config={
                    'response_mime_type': 'application/json',
                    'response_schema': ReplyAnalysis.model_json_schema(),
                },
            )
            return ReplyAnalysis.model_validate(json.loads(resp.text))
        except Exception as e:
            events.event('ERROR', component='gemini_reply_analysis', error=str(e))
            return ReplyAnalysis(
                interested=False,
                urgency='normal',
                summary='Gemini analysis failed.',
                recommended_action='Owner review required.',
                reply='Thanks for getting back to us. I will review your message and follow up shortly.',
            )

    def sales_reply(self, conversation, customer_question):
        if not self.client:
            return 'I can help with package options, deliverables, turnaround, and onboarding steps.'
        try:
            return self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=(
                    f'You are the sales agent for Pixel Pulse Studio. '
                    f'Packages: {PACKAGES}. Do not invent capabilities. '
                    f'Conversation: {json.dumps(conversation)} Question: {customer_question}'
                ),
            ).text.strip()
        except Exception as e:
            events.event('ERROR', component='gemini_sales', error=str(e))
            return 'Thanks for your message. I need the owner to review that request.'

    def presentation_strategy(self, onboarding, source_text):
        if not self.client:
            return self._fallback_presentation(onboarding, source_text)
        prompt = (
            f'Create a truthful, visually varied presentation strategy. Never fabricate facts. '
            f'Use only supplied onboarding and source material. Missing facts should become useful '
            f'instructions, not generic placeholders. Return JSON with style and slides, each slide '
            f'having layout,title,bullets. Onboarding: {json.dumps(onboarding)} '
            f'Source: {source_text[:12000]}'
        )
        try:
            result = json.loads(
                self.client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config={'response_mime_type': 'application/json'},
                ).text
            )
            return result if result.get('slides') else self._fallback_presentation(onboarding, source_text)
        except Exception as e:
            events.event('ERROR', component='gemini_strategy', error=str(e))
            return self._fallback_presentation(onboarding, source_text)

    def _fallback_presentation(self, onboarding, source_text):
        data = {str(k): str(v).strip() for k, v in (onboarding or {}).items() if v not in (None, '')}
        company = data.get('company_name', 'Company')
        industry = data.get('industry', 'business')
        service = data.get('service', 'Presentation')
        objective = data.get('objective') or data.get('goal') or 'Present the business clearly and professionally.'
        audience = data.get('audience') or 'Business decision makers'
        msg = data.get('key_message') or data.get('message') or 'Clear communication of the company offering.'
        evidence = 'Verified source material was supplied.' if source_text else 'No supporting source material was supplied; proof points are not invented.'
        slides = [
            {'layout': 'TITLE', 'title': company, 'bullets': [service, f'Prepared for {audience}']},
            {'layout': 'OVERVIEW', 'title': 'Purpose', 'bullets': [objective, f'Audience: {audience}']},
            {'layout': 'TWO_COLUMN', 'title': 'Company at a glance', 'bullets': [f'{company} operates in the {industry} space.', f'Focus: {service}.']},
            {'layout': 'QUOTE', 'title': 'Core message', 'bullets': [msg]},
            {'layout': 'EVIDENCE', 'title': 'Evidence and proof', 'bullets': [evidence, 'Add verified case studies or testimonials when available.']},
            {'layout': 'STATS', 'title': 'Market context', 'bullets': ['Add verified market size', 'Add verified growth rate', 'Add verified customer count']},
            {'layout': 'TIMELINE', 'title': 'Recommended approach', 'bullets': ['Clarify the audience need', 'Present the offering', 'Support with verified evidence', 'Close with the requested action']},
            {'layout': 'CTA', 'title': 'Next step', 'bullets': [objective]},
            {'layout': 'OVERVIEW', 'title': 'Key takeaways', 'bullets': [msg, 'Use verified evidence to strengthen the final version.']},
            {'layout': 'CTA', 'title': 'Contact', 'bullets': [data.get('email', ''), 'Pixel Pulse Studio']},
        ]
        return {'style': data.get('style', 'Premium Minimal'), 'slides': slides}
