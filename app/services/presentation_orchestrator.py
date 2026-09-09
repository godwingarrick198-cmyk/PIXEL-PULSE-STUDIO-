import logging
import os

from sqlalchemy import select

from app.models.entities import OnboardingForm
from app.services.presentation import PresentationService
from app.services.presenton import PresentonService


log = logging.getLogger(__name__)


class PresentationOrchestrator(PresentationService):
    """Use Presenton when configured; keep the local renderer as a hard fallback."""

    def __init__(self):
        super().__init__()
        self.presenton = PresentonService()

    def generate(self, db, order_id):
        project = super().generate(db, order_id)
        if not self.presenton.enabled:
            return project

        try:
            form = db.scalar(select(OnboardingForm).where(OnboardingForm.order_id == order_id))
            data = form.data if form else {}
            source_text = self._source_text(db, order_id)
            slides = len(project.strategy_json.get('slides', [])) or 8
            content = "\n\n".join([
                f"Company: {data.get('company_name', '')}",
                f"Industry: {data.get('industry', '')}",
                f"Service / presentation type: {data.get('service', data.get('presentation_type', ''))}",
                f"Purpose: {data.get('purpose', data.get('objective', ''))}",
                f"Audience: {data.get('audience', '')}",
                f"Key message: {data.get('key_message', '')}",
                f"Customer notes: {data.get('notes', '')}",
                f"Source material:\n{source_text[:12000]}",
            ])
            instructions = (
                "Create a client-ready, visually rich, editable PowerPoint. "
                "Use the customer's actual information and source material; do not invent metrics, "
                "customers, logos, testimonials, revenue, or statistics. Prefer cards, panels, diagrams, "
                "visual hierarchy, concise copy, and varied layouts over bullet-heavy pages. "
                f"Requested style: {data.get('style', project.strategy_json.get('style', 'professional'))}. "
                "Use charts only when the supplied information contains real numeric data. "
                "If no logo is supplied, use clean typography rather than inventing a logo."
            )

            base = os.path.join('storage', 'projects', str(order_id))
            result = self.presenton.generate(content, instructions, slides)
            self.presenton.download(result['pptx_url'], os.path.join(base, 'presentation.pptx'))
            self.presenton.download(result['pdf_url'], os.path.join(base, 'presentation.pdf'))
            project.pptx_path = os.path.join(base, 'presentation.pptx')
            project.pdf_path = os.path.join(base, 'presentation.pdf')
            db.commit()
            db.refresh(project)
        except Exception:
            log.exception("Presenton generation failed; keeping local presentation fallback")

        return project
