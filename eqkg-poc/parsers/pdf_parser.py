"""PDF 解析器 — PyMuPDF 文字层提取。"""
from __future__ import annotations

import io

from parsers.base import BaseParser, register_parser


@register_parser(".pdf")
class PdfParser(BaseParser):
    """PDF 文字层提取。返回空串表示扫描件（应走 OCR）。"""

    supported_ext = ".pdf"

    def extract(self, file_bytes: bytes) -> str:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise RuntimeError("PyMuPDF 未安装。请: py -3.12 -m pip install pymupdf")

        doc = fitz.open(stream=io.BytesIO(file_bytes), filetype="pdf")
        try:
            pages = [doc[p].get_text() for p in range(doc.page_count)]
        finally:
            doc.close()
        return "\n".join(pages)
