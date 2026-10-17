"""文档解析策略层。

所有解析器继承 BaseParser，用 @register_parser 自动注册。
get_parser(".pdf") 返回对应实例，parser.extract(bytes) → str。

用法:
    from parsers import get_parser, list_supported_exts
    parser = get_parser(".pdf")
    text = parser.extract(file_bytes)
"""
from parsers.base import BaseParser, register_parser, get_parser, list_supported_exts

# 注册所有解析器（import 即触发装饰器）
import parsers.pdf_parser
import parsers.docx_parser  # 可选
import parsers.ocr_parser   # stub：Tesseract 未装时给出友好提示

__all__ = ["BaseParser", "register_parser", "get_parser", "list_supported_exts"]
