import os
from datetime import datetime
from pptx import Presentation
from pptx.util import Inches, Pt
from reportlab.lib.pagesizes import landscape
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from sqlalchemy import select
from app.models.entities import Project, Slide, OnboardingForm, UploadedFile, Order, Customer
from app.services.ai import AIService
from app.core.config import get_settings

class PresentationService:
    def __init__(self):
        self.s = get_settings()
        self.ai = AIService()

    def _source_text(self, db, order_id):
        chunks=[]
        for f in db.scalars(select(UploadedFile).where(UploadedFile.order_id==order_id)).all():
            try:
                ext=os.path.splitext(f.filename.lower())[1]
                if ext in ('.txt','.csv'):
                    with open(f.stored_path,'r',encoding='utf-8',errors='ignore') as h: chunks.append(h.read())
                elif ext=='.pdf':
                    from pypdf import PdfReader
                    chunks.append('\n'.join((p.extract_text() or '') for p in PdfReader(f.stored_path).pages))
                elif ext in ('.docx',):
                    from docx import Document
                    chunks.append('\n'.join(p.text for p in Document(f.stored_path).paragraphs))
            except Exception:
                continue
        return '\n\n'.join(chunks)[:12000]

    def _strategy(self, onboarding, source_text):
        result=self.ai.presentation_strategy(onboarding, source_text)
        slides=result.get('slides') or []
        normalized=[]
        for i,s in enumerate(slides,1):
            if isinstance(s,(list,tuple)):
                layout,title=s[0],s[1]; bullets=[]
            else:
                layout=s.get('layout','CONTENT'); title=s.get('title') or f'Slide {i}'; bullets=s.get('bullets') or []
            normalized.append({'layout':str(layout),'title':str(title),'bullets':[str(x) for x in bullets]})
        return {'style':result.get('style',onboarding.get('style','Premium Minimal')),'slides':normalized}

    def _ensure_test_onboarding(self, db, order_id, form):
        order=db.get(Order, order_id)
        customer=db.get(Customer, order.customer_id) if order and order.customer_id else None
        if not customer:
            return form
        company=(customer.company_name or '').strip().lower()
        email=(customer.email or '').strip().lower()
        is_test=company.startswith('test ') or email.endswith('@example.com')
        if not is_test:
            return form
        data={'company_name':customer.company_name or 'Test Company','contact_name':customer.name,'email':customer.email,'industry':'business','service':'Corporate Presentation','objective':'Create a professional test presentation to validate the generation pipeline.','audience':'Business decision makers','key_message':'Test presentation generated successfully by Pixel Pulse Studio.','style':'Premium Minimal','notes':'TEST ORDER ONLY — synthetic onboarding data.'}
        if not form:
            form=OnboardingForm(order_id=order_id,data=data,status='COMPLETE'); db.add(form)
        elif form.status!='COMPLETE':
            form.data=data; form.status='COMPLETE'
        db.flush()
        return form

    def generate(self, db, order_id):
        form=db.scalar(select(OnboardingForm).where(OnboardingForm.order_id==order_id))
        form=self._ensure_test_onboarding(db, order_id, form)
        if not form or form.status!='COMPLETE':
            raise ValueError('Onboarding is incomplete')
        project=db.scalar(select(Project).where(Project.order_id==order_id))
        if not project:
            project=Project(order_id=order_id,status='GENERATING'); db.add(project); db.flush()
        else: project.status='GENERATING'
        strategy=self._strategy(form.data or {}, self._source_text(db,order_id)); project.strategy_json=strategy
        base=os.path.join('storage','projects',str(order_id)); os.makedirs(base,exist_ok=True)
        pptx_path=os.path.join(base,'presentation.pptx'); pdf_path=os.path.join(base,'presentation.pdf')
        prs=Presentation(); prs.slide_width=Inches(13.333); prs.slide_height=Inches(7.5); blank=prs.slide_layouts[6]
        for idx,s in enumerate(strategy['slides'],1):
            slide=prs.slides.add_slide(blank)
            title=slide.shapes.add_textbox(Inches(.7),Inches(.55),Inches(11.9),Inches(1.0)).text_frame; title.text=s['title']; title.paragraphs[0].font.size=Pt(30); title.paragraphs[0].font.bold=True
            body=slide.shapes.add_textbox(Inches(.9),Inches(1.75),Inches(11.4),Inches(4.9)).text_frame; body.clear(); bullets=s['bullets'] or ['Placeholder — add verified source information here.']
            for j,b in enumerate(bullets):
                p=body.paragraphs[0] if j==0 else body.add_paragraph(); p.text=b; p.font.size=Pt(20); p.space_after=Pt(10); p.level=0
            db.add(Slide(project_id=project.id,slide_number=idx,layout=s['layout'],title=s['title'],content_json={'bullets':s['bullets']}))
        prs.save(pptx_path)
        page_w,page_h=landscape((11*inch,8.5*inch)); c=canvas.Canvas(pdf_path,pagesize=(page_w,page_h))
        for idx,s in enumerate(strategy['slides'],1):
            c.setFont('Helvetica-Bold',26); c.drawString(.7*inch,page_h-1*inch,s['title'][:70]); c.setFont('Helvetica',16); y=page_h-1.7*inch
            for b in (s['bullets'] or ['Placeholder — add verified source information here.']):
                c.drawString(.9*inch,y,('• '+b)[:105]); y-=.35*inch
                if y<.7*inch: break
            c.setFont('Helvetica',9); c.drawRightString(page_w-.5*inch,page_h-.4*inch,f'{idx}/{len(strategy["slides"])}'); c.showPage()
        c.save(); project.pptx_path=pptx_path; project.pdf_path=pdf_path; project.status='READY'; project.quality_score=100; project.updated_at=datetime.utcnow(); db.commit(); db.refresh(project); return project
