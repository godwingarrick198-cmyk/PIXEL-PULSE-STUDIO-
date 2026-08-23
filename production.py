from sqlalchemy import select
from app.models.entities import Order, OnboardingForm, UploadedFile, Project, Delivery
from app.services.presentation import PresentationService
from app.services.qc import QCService
from app.services.delivery import DeliveryService
from app.core.config import get_settings
from app.core.logging import events
from pathlib import Path

REQUIRED=['customer_name','company_name','email','presentation_type','purpose','audience','number_of_slides','style']
class ProductionService:
    def __init__(self): self.s=get_settings(); self.pres=PresentationService(); self.qc=QCService(); self.delivery=DeliveryService()
    def onboarding_complete(self,data): return all(data.get(k) not in (None,'',[]) for k in REQUIRED)
    def run(self,db,order_id):
        o=db.get(Order,order_id)
        if not o or o.status not in ('PAID','IN_PRODUCTION'): return None
        form=db.scalar(select(OnboardingForm).where(OnboardingForm.order_id==o.id))
        if not form or not self.onboarding_complete(form.data): return 'WAITING_ONBOARDING'
        files=db.scalars(select(UploadedFile).where(UploadedFile.order_id==o.id)).all()
        p=db.scalar(select(Project).where(Project.order_id==o.id))
        if not p: p=Project(order_id=o.id,status='IN_PRODUCTION'); db.add(p); db.commit(); db.refresh(p)
        try:
            pptx,pdf,strategy=self.pres.build(o.id,form.data,[f.stored_path for f in files]); p.pptx_path=pptx;p.pdf_path=pdf;p.strategy_json=strategy;p.status='QC';db.commit();events.event('QC_STARTED',order_id=o.order_id)
            score,issues=self.qc.inspect(pptx)
            p.quality_score=score
            if score<self.s.MIN_PRESENTATION_QUALITY_SCORE:
                p.repair_attempts+=1
                if p.repair_attempts<=self.s.MAX_AUTO_REPAIR_ATTEMPTS:
                    p.status='REPAIRING'; db.commit(); return self.run(db,order_id)
                p.status='REQUIRES_HUMAN'; o.status='REQUIRES_HUMAN'; db.commit(); events.event('HUMAN_REQUIRED',order_id=o.order_id,issues=issues); return 'REQUIRES_HUMAN'
            p.status='READY';o.status='DELIVERED';db.commit();d=self.delivery.create(db,o.id);events.event('DELIVERY_COMPLETED',order_id=o.order_id,quality_score=score);return d
        except Exception as e:
            p.status='REQUIRES_HUMAN';o.status='REQUIRES_HUMAN';db.commit();events.event('ERROR',component='production',order_id=o.order_id,error=str(e));return 'REQUIRES_HUMAN'
