from app.services.presentation import PresentationService


class PresentationOrchestrator(PresentationService):
    """Presentation pipeline powered by Gemini for strategy/content and the local renderer for PPTX/PDF output."""

    def __init__(self):
        super().__init__()

    def generate(self, db, order_id):
        # Gemini creates the presentation strategy/content through AIService.
        # PresentationService then renders that strategy into editable PPTX and PDF.
        return super().generate(db, order_id)
