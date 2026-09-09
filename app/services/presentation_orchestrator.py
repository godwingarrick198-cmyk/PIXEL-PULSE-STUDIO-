import os

from app.services.presentation import PresentationService
from app.services.presenton import PresentonService


class PresentationOrchestrator(PresentationService):
    """Generate with the existing safe fallback, or Presenton when enabled.

    The fallback is deliberately retained so Pixel Pulse never loses the
    ability to deliver a deck just because the optional Presenton service is
    sleeping, unavailable, or temporarily misconfigured.
    """

    def __init__(self):
        super().__init__()
        self.presenton = PresentonService()

    def generate(self, db, order_id):
        project = super().generate(db, order_id)
        if not self.presenton.enabled:
            return project

        onboarding = db.get(__import__('app.models.entities', fromlist=['Order']).Order, order_id)
        form = db.scalar(__import__('sqlalchemy', fromlist=['select']).select(__import__('app.models.entities', fromlist=['OnboardingForm']).OnboardingForm).where(__import__('app.models.entities', fromlist=['OnboardingForm']).OnboardingForm.order_id == order_id))
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
        return project
