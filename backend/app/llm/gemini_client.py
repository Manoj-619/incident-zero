from __future__ import annotations

import json
from typing import Any

import google.generativeai as genai

from app.config import Settings


class GeminiClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._enabled = bool(settings.gemini_api_key)
        if self._enabled:
            genai.configure(api_key=settings.gemini_api_key)
            self._model = genai.GenerativeModel(settings.gemini_model)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def generate_json(self, system: str, user: str) -> dict[str, Any]:
        if not self._enabled:
            raise RuntimeError("Gemini API key not configured")
        prompt = f"{system}\n\n---\n\n{user}\n\nRespond with valid JSON only."
        response = self._model.generate_content(prompt)
        text = (response.text or "").strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            if text.endswith("```"):
                text = text[:-3]
        return json.loads(text)
