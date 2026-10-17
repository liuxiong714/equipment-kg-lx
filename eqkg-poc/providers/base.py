"""LLM Provider 抽象基类。"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger("eqkg")


class LLMProvider(ABC):
    """LLM 后端抽象。子类必须实现 generate(prompt, **kw) → str。"""

    name: str = "base"

    @abstractmethod
    def generate(self, prompt: str, *, timeout: int = 120, **kwargs) -> str:
        """非流式生成。失败返回空串。"""
        ...

    def health_check(self) -> bool:
        """快速连通性检查（默认 True）。"""
        return True


class NullProvider(LLMProvider):
    """永远返回空串 —— CPU 禁用 LLM 时的安全占位。"""
    name = "null"

    def generate(self, prompt: str, *, timeout: int = 120, **kwargs) -> str:
        return ""


# -------- 工厂 --------
_PROVIDERS: dict[str, type[LLMProvider]] = {}


def register_provider(name: str):
    def decorator(cls):
        _PROVIDERS[name.lower()] = cls
        return cls
    return decorator


def get_provider(name: str = "ollama", **kwargs) -> LLMProvider:
    """按名称取 Provider 实例。未知名 → NullProvider。"""
    cls = _PROVIDERS.get(name.lower())
    if cls:
        return cls(**kwargs)
    logger.warning(f"[LLM] 未知 provider: {name}，返回 NullProvider。可用: {list(_PROVIDERS.keys())}")
    return NullProvider()
