"""LLM Provider 抽象层。

支持 Ollama / OpenAI 等后端切换，接口统一：
    provider.generate(prompt) → str

设计目标：
- 当前 CPU 下仅用于 Text2Cypher 兜底
- 将来 GPU 就绪后直接在 providers/ 上加 ollama_provider.py 的 stream 模式
- 不破坏 qa_engine.py 现有 requests.post 调用
"""
from providers.base import LLMProvider, get_provider

# 注册所有 Provider（import 即触发装饰器）
import providers.ollama_provider

__all__ = ["LLMProvider", "get_provider"]
