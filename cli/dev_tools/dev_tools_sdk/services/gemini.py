from __future__ import annotations


class GeminiService:
    """Cloud review fallback service.

    This intentionally provides a lightweight interface; transport integration can
    be wired incrementally behind this contract.
    """

    def review(self, prompt: str) -> str:
        return "[Gemini fallback placeholder] " + prompt[:200]
