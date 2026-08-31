import json
from pydantic import BaseModel, Field
from app.core.config import get_settings
from app.core.logging import events

SERVICES={'startup':'Investor Pitch Deck','saas':'Investor/Sales Deck','technology company':'Investor/Sales Deck','marketing agency':'Client Sales Deck','agency':'Client Sales Deck','consultant':'Proposal Deck','consulting':'Proposal Deck','real estate':'Property/Investment Presentation','property':'Property/Investment Presentation','corporate':'Corporate Presentation','business':'Corporate Presentation','coach':'Webinar/Training Presentation','education':'Training Presentation','e-commerce':'Product Presentation','product':'Product Presentation','webinar':'Webinar Presentation','training':'Training Presentation'}
PACKAGES={'STARTER':(10,250),'PROFESSIONAL':(20,500),'PREMIUM':(30,1000)}

class Qualification(BaseModel):
    qualified: bool
    score: int = Field(ge=0,le=100)
    company_type: str
    recommended_service: str
    estimated_budget: float
    purchase_likelihood: float = Field(ge=0,le=1)
    reason: str
    personalization_points: list[str] = []
    recommended_channel: str = 'email'

class AIService:
    def __init__(self):
        self.settings=get_settings(); self.client=None
        if self.settings.GEMINI_API_KEY:
            try:
                from google import genai
                self.client=genai.Client(api_key=self.settings.GEMINI_API_KEY)
            except Exception as e: events.event('ERROR',component='gemini_init',error=str(e))

    def _fallback(self,prospect):
        text=' '.join(str(prospect.get(k) or '') for k in ('company_name','industry','description')).lower()
        service=next((v for k,v in SERVICES.items() if k in text),None)
        if not service: return Qualification(qualified=False,score=0,company_type='unknown',recommended_service='SKIP',estimated_budget=0,purchase_likelihood=0,reason='No configured service match.')
        return Qualification(qualified=True,score=85 if prospect.get('website') else 80,company_type=prospect.get('industry') or 'business',recommended_service=service,estimated_budget=500,purchase_likelihood=.55,reason='Public business signals match a configured presentation service.',personalization_points=[prospect.get('company_name','')],recommended_channel='email')

    def qualify(self,prospect):
        if not self.client: return self._fallback(prospect)
        prompt=f'''You qualify prospects for Pixel Pulse Studio, a professional presentation-design business. Never invent facts. Use only supplied data. Configured services: {sorted(set(SERVICES.values()))}. Prospect: {json.dumps(prospect,default=str)} Return structured JSON with qualified, score 0-100, company_type, recommended_service (or SKIP), estimated_budget, purchase_likelihood 0-1, reason, personalization_points, recommended_channel.'''
        try:
            resp=self.client.models.generate_content(model='gemini-2.5-flash',contents=prompt,config={'response_mime_type':'application/json','response_schema':Qualification.model_json_schema()})
            return Qualification.model_validate(json.loads(resp.text))
        except Exception as e: events.event('ERROR',component='gemini_qualification',error=str(e)); return self._fallback(prospect)

    def generate_outreach(self,prospect,service):
        name=prospect.get('contact_name') or prospect.get('founder_name') or 'there'; company=prospect.get('company_name') or 'your company'; subject=f'{service} for {company}'
        body=f'Hi {name},\n\nPixel Pulse Studio creates professional {service.lower()}s for businesses that need clear, polished presentations. Based on public information about {company}, I thought this service could be relevant to your team.\n\nWe handle the strategy, editable PowerPoint design, and final PDF delivery. If presentation support is useful, I can share the package options and turnaround.\n\nBest,\nPixel Pulse Studio'
        return subject,body

    def sales_reply(self,conversation,customer_question):
        if not self.client: return 'I can help with package options, deliverables, turnaround, and the onboarding steps. For anything outside those areas, I will have the owner review it.'
        prompt=f'''You are the sales agent for Pixel Pulse Studio. Packages: {PACKAGES}. Do not promise outcomes. Do not invent capabilities. Answer only the customer's question. Conversation: {json.dumps(conversation)} Question: {customer_question}'''
        try: return self.client.models.generate_content(model='gemini-2.5-flash',contents=prompt).text.strip()
        except Exception as e: events.event('ERROR',component='gemini_sales',error=str(e)); return 'Thanks for your message. I need the owner to review that request before I confirm it.'

    def _fallback_presentation(self,onboarding,source_text):
        """Deterministic zero-cost deck content. Uses only supplied onboarding/source data; never invents business facts."""
        data={str(k):str(v).strip() for k,v in (onboarding or {}).items() if v not in (None,'')}
        company=data.get('company_name','Company')
        contact=data.get('contact_name')
        email=data.get('email')
        industry=data.get('industry','business')
        service=data.get('service','Presentation')
        objective=data.get('objective') or data.get('goal') or 'Present the business clearly and professionally.'
        audience=data.get('audience') or 'Business decision makers'
        key_message=data.get('key_message') or data.get('message') or 'Clear, professional communication of the company offering.'
        description=data.get('description') or data.get('about')
        source=source_text.strip() if source_text else ''
        slides=[
            {'layout':'TITLE','title':company,'bullets':[service, f'Prepared for {audience}']},
            {'layout':'OVERVIEW','title':'Purpose','bullets':[objective, f'Audience: {audience}']},
            {'layout':'CONTENT','title':'Company at a glance','bullets':[f'{company} operates in the {industry} space.'] + ([description] if description else [])},
            {'layout':'CONTENT','title':'Core message','bullets':[key_message]},
            {'layout':'CONTENT','title':'Offering','bullets':[f'Recommended presentation: {service}.', 'The final deck should clearly explain the offering, value, and next action using verified customer information.']},
            {'layout':'CONTENT','title':'Audience value','bullets':[f'The presentation is designed for {audience}.', 'Lead with the audience problem, then connect the offering to the requested outcome.']},
            {'layout':'CONTENT','title':'Evidence and proof','bullets':(['Verified source material was supplied with this order.'] if source else ['No supporting source material was supplied; proof points are intentionally not invented.'])},
            {'layout':'CONTENT','title':'Market context','bullets':['Market size, customer counts, growth rates, and competitor claims should be added only when verified source material is supplied.']},
            {'layout':'CONTENT','title':'Business case','bullets':['Use verified pricing, process, outcomes, and differentiators from the customer onboarding or uploaded source material.','Unverified claims are intentionally excluded.']},
            {'layout':'CONTENT','title':'Recommended next step','bullets':['Align the final call to action with the customer objective.', objective]},
            {'layout':'CONTENT','title':'Key takeaways','bullets':[f'{company}: {key_message}',f'Focus: {objective}','Use verified evidence to strengthen the final version.']},
            {'layout':'CONTACT','title':'Contact','bullets':([contact] if contact else []) + ([email] if email else []) + ['Pixel Pulse Studio']}
        ]
        return {'style':data.get('style','Premium Minimal'),'slides':slides}

    def presentation_strategy(self,onboarding,source_text):
        if not self.client:
            return self._fallback_presentation(onboarding,source_text)
        prompt=f'''Create a truthful presentation strategy for Pixel Pulse Studio. Never fabricate facts. Use only supplied onboarding and source material. Do not invent market numbers, customers, competitors, traction, team members, pricing, or contact details. If information is missing, omit the claim and use a useful instruction such as "Add verified proof point from customer source material" rather than a generic placeholder. Onboarding: {json.dumps(onboarding)} Source materials: {source_text[:12000]} Return JSON with style and slides, each slide having layout,title,bullets.'''
        try:
            result=json.loads(self.client.models.generate_content(model='gemini-2.5-flash',contents=prompt,config={'response_mime_type':'application/json'}).text)
            if not result.get('slides'): return self._fallback_presentation(onboarding,source_text)
            return result
        except Exception as e:
            events.event('ERROR',component='gemini_strategy',error=str(e)); return self._fallback_presentation(onboarding,source_text)
