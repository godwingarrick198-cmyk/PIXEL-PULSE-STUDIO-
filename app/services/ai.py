import json
from pydantic import BaseModel, Field
from app.core.config import get_settings
from app.core.logging import events

GEMINI_MODEL='gemini-3.6-flash'
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
        prompt=f'''You qualify prospects for Pixel Pulse Studio. Never invent facts. Use only supplied data. Prospect: {json.dumps(prospect,default=str)} Return JSON with qualified, score 0-100, company_type, recommended_service, estimated_budget, purchase_likelihood 0-1, reason, personalization_points, recommended_channel.'''
        try:
            resp=self.client.models.generate_content(model=GEMINI_MODEL,contents=prompt,config={'response_mime_type':'application/json','response_schema':Qualification.model_json_schema()})
            return Qualification.model_validate(json.loads(resp.text))
        except Exception as e: events.event('ERROR',component='gemini_qualification',error=str(e)); return self._fallback(prospect)

    def generate_outreach(self,prospect,service):
        name=prospect.get('contact_name') or prospect.get('founder_name') or 'there'; company=prospect.get('company_name') or 'your company'; return f'{service} for {company}',f'Hi {name},\n\nPixel Pulse Studio creates professional {service.lower()}s for businesses that need clear, polished presentations. Based on public information about {company}, I thought this service could be relevant to your team.\n\nWe handle the strategy, editable PowerPoint design, and final PDF delivery. If presentation support is useful, I can share the package options and turnaround.\n\nBest,\nPixel Pulse Studio'

    def sales_reply(self,conversation,customer_question):
        if not self.client: return 'I can help with package options, deliverables, turnaround, and onboarding steps.'
        try: return self.client.models.generate_content(model=GEMINI_MODEL,contents=f'You are the sales agent for Pixel Pulse Studio. Packages: {PACKAGES}. Do not invent capabilities. Conversation: {json.dumps(conversation)} Question: {customer_question}').text.strip()
        except Exception as e: events.event('ERROR',component='gemini_sales',error=str(e)); return 'Thanks for your message. I need the owner to review that request.'

    def presentation_strategy(self,onboarding,source_text):
        if not self.client: return self._fallback_presentation(onboarding,source_text)
        prompt=f'''Create a truthful, visually varied presentation strategy. Never fabricate facts. Use only supplied onboarding and source material. Missing facts should become useful instructions, not generic placeholders. Return JSON with style and slides, each slide having layout,title,bullets. Onboarding: {json.dumps(onboarding)} Source: {source_text[:12000]}'''
        try:
            result=json.loads(self.client.models.generate_content(model=GEMINI_MODEL,contents=prompt,config={'response_mime_type':'application/json'}).text)
            return result if result.get('slides') else self._fallback_presentation(onboarding,source_text)
        except Exception as e: events.event('ERROR',component='gemini_strategy',error=str(e)); return self._fallback_presentation(onboarding,source_text)

    def _fallback_presentation(self,onboarding,source_text):
        data={str(k):str(v).strip() for k,v in (onboarding or {}).items() if v not in (None,'')}; company=data.get('company_name','Company'); industry=data.get('industry','business'); service=data.get('service','Presentation'); objective=data.get('objective') or data.get('goal') or 'Present the business clearly and professionally.'; audience=data.get('audience') or 'Business decision makers'; msg=data.get('key_message') or data.get('message') or 'Clear communication of the company offering.'; evidence='Verified source material was supplied.' if source_text else 'No supporting source material was supplied; proof points are not invented.'
        slides=[{'layout':'TITLE','title':company,'bullets':[service,f'Prepared for {audience}']},{'layout':'OVERVIEW','title':'Purpose','bullets':[objective,f'Audience: {audience}']},{'layout':'TWO_COLUMN','title':'Company at a glance','bullets':[f'{company} operates in the {industry} space.',f'Focus: {service}.']},{'layout':'QUOTE','title':'Core message','bullets':[msg]},{'layout':'EVIDENCE','title':'Evidence and proof','bullets':[evidence,'Add verified case studies or testimonials when available.']},{'layout':'STATS','title':'Market context','bullets':['Add verified market size','Add verified growth rate','Add verified customer count']},{'layout':'TIMELINE','title':'Recommended approach','bullets':['Clarify the audience need','Present the offering','Support with verified evidence','Close with the requested action']},{'layout':'CTA','title':'Next step','bullets':[objective]},{'layout':'OVERVIEW','title':'Key takeaways','bullets':[msg,'Use verified evidence to strengthen the final version.']},{'layout':'CTA','title':'Contact','bullets':[data.get('email',''),'Pixel Pulse Studio']}]
        return {'style':data.get('style','Premium Minimal'),'slides':slides}
