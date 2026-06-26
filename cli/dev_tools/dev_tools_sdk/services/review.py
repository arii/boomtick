from __future__ import annotations


class ReviewService:
    def build_prompt(self, context: str) -> str:
        return f"Review the following context and provide actionable fixes:\n\n{context}"
