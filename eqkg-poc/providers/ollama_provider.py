"""Ollama Provider —— 本地部署模型。"""
from __future__ import annotations

import requests

from providers.base import LLMProvider, register_provider


@register_provider("ollama")
class OllamaProvider(LLMProvider):
    """封装 Ollama /api/generate。"""

    name = "ollama"

    def __init__(self, url: str = "http://localhost:11434", model: str = "qwen2.5:7b"):
        self.url = url.rstrip("/")
        self.model = model

    def generate(self, prompt: str, *, timeout: int = 120, **kwargs) -> str:
        try:
            resp = requests.post(
                f"{self.url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    **kwargs,
                },
                timeout=timeout,
            )
            if resp.status_code != 200:
                return ""
            return resp.json().get("response", "").strip()
        except Exception:
            return ""

    def health_check(self) -> bool:
        try:
            resp = requests.get(f"{self.url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False


@register_provider("openai")
class OpenAIProvider(LLMProvider):
    """OpenAI 兼容接口（未来可以切云端）。"""

    name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", base_url: str = "https://api.openai.com/v1"):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    def generate(self, prompt: str, *, timeout: int = 120, **kwargs) -> str:
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    **kwargs,
                },
                timeout=timeout,
            )
            if resp.status_code != 200:
                return ""
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception:
            return ""
