import os
from pathlib import Path

import httpx

from app.core.config import get_settings


class PresentonService:
    """Optional Presenton adapter.

    Presenton stays external to Pixel Pulse. Pixel Pulse sends the approved
    onboarding/content to a self-hosted Presenton instance, then downloads the
    generated PPTX/PDF into its normal order storage.
    """

    def __init__(self):
        self.s = get_settings()

    @property
    def enabled(self):
        return bool(self.s.PRESENTON_ENABLED and self.s.PRESENTON_URL and self.s.PRESENTON_API_KEY)

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.s.PRESENTON_API_KEY}",
            "Content-Type": "application/json",
        }

    def generate(self, content, instructions, slides, template="general"):
        if not self.enabled:
            raise RuntimeError("Presenton is not configured")
        url = self.s.PRESENTON_URL.rstrip("/") + "/api/v1/ppt/presentation/generate"
        payload = {
            "content": content,
            "instructions": instructions,
            "n_slides": slides,
            "language": "English",
            "template": template,
            "tone": "professional",
            "verbosity": "standard",
            "include_title_slide": True,
            "include_table_of_contents": False,
            "export_as": "pptx",
        }
        with httpx.Client(timeout=self.s.PRESENTON_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = client.post(url, headers=self._headers(), json=payload)
            response.raise_for_status()
            ppt = response.json()

            pdf_payload = dict(payload)
            pdf_payload["export_as"] = "pdf"
            response = client.post(url, headers=self._headers(), json=pdf_payload)
            response.raise_for_status()
            pdf = response.json()

            return {
                "pptx_url": self.s.PRESENTON_URL.rstrip("/") + ppt["path"],
                "pdf_url": self.s.PRESENTON_URL.rstrip("/") + pdf["path"],
                "edit_url": self.s.PRESENTON_URL.rstrip("/") + (ppt.get("edit_path") or ""),
            }

    def download(self, url, destination):
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=self.s.PRESENTON_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            with open(destination, "wb") as handle:
                handle.write(response.content)
        return destination
