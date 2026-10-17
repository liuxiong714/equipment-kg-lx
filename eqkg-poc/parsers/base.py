"""BaseParser 基类 + 全局注册表。"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger("eqkg")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


_PARSER_REGISTRY: dict[str, type[BaseParser]] = {}


def register_parser(ext: str):
    """装饰器：把解析器类注册到全局注册表。"""
    def decorator(cls: type[BaseParser]):
        key = ext.lower().lstrip(".")
        if key in _PARSER_REGISTRY:
            logger.warning(f"[Parser] 覆盖注册: .{key} 原={_PARSER_REGISTRY[key].__name__} 新={cls.__name__}")
        _PARSER_REGISTRY[key] = cls
        return cls
    return decorator


def get_parser(file_ext: str) -> Optional[BaseParser]:
    """按扩展名取解析器实例（无状态，可复用）。"""
    key = file_ext.lower().lstrip(".")
    cls = _PARSER_REGISTRY.get(key)
    if cls:
        return cls()
    logger.warning(f"[Parser] 未找到 .{key} 的解析器，可用: {list(_PARSER_REGISTRY.keys())}")
    return None


def list_supported_exts() -> list[str]:
    """返回所有已注册扩展名。"""
    return [f".{k}" for k in _PARSER_REGISTRY.keys()]


class BaseParser(ABC):
    """解析器基类。子类定义 supported_ext 并实现 extract()。"""

    supported_ext: str = ""

    @abstractmethod
    def extract(self, file_bytes: bytes) -> str:
        """从文件字节提取纯文本。返回空串=解析失败/扫描件。"""
        ...

    def extract_text(self, file_bytes: bytes) -> str:
        """带日志包装的 extract。"""
        name = self.__class__.__name__
        try:
            text = self.extract(file_bytes)
            if text and text.strip():
                logger.info(f"[{name}] ✅ {len(text)} 字符")
            else:
                logger.warning(f"[{name}] ⚠ 文本为空 (可能扫描件/空文件)")
            return text or ""
        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"[{name}] ❌ 解析异常: {e}")
            return ""
