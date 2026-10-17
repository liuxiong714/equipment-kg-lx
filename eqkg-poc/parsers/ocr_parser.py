"""OCR 解析器 — 扫描件 PDF / 图片。

需要先装:
  1. Tesseract 本体: winget install Ubi.Integer.TesseractOCR
  2. Python 绑定: py -3.12 -m pip install pytesseract pillow pymupdf
  3. 中文语言包: https://github.com/UB-Mannheim/tesseract/wiki 选 chi_sim

用法：当 PdfParser 返回空串时，调用方应该自动 fallback 到 OcrParser。
"""
from __future__ import annotations

import io
import tempfile

from parsers.base import BaseParser, register_parser

# 支持的图片格式
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}


@register_parser(".png")
@register_parser(".jpg")
@register_parser(".jpeg")
@register_parser(".tif")
@register_parser(".tiff")
@register_parser(".bmp")
class ImageParser(BaseParser):
    """单张图片 OCR（作为 .pdf OCR 处理的基础能力）。"""

    supported_ext = ".png"

    def extract(self, file_bytes: bytes) -> str:
        try:
            import pytesseract
            from PIL import Image
        except ImportError as e:
            raise RuntimeError(f"OCR 依赖缺失: {e}. 请装 pytesseract + pillow + Tesseract 本体")

        img = Image.open(io.BytesIO(file_bytes))
        return pytesseract.image_to_string(img, lang="chi_sim+eng")


def _pdf_pages_to_images(pdf_bytes: bytes) -> list[bytes]:
    """把 PDF 每页渲染成 PNG bytes（OCR 输入）。"""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return []
    doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
    try:
        results = []
        for page_num in range(min(doc.page_count, 30)):  # 上限 30 页防止 OCR 卡爆
            page = doc[page_num]
            pix = page.get_pixmap(dpi=200)
            png = pix.tobytes("png")
            results.append(png)
        return results
    finally:
        doc.close()


class OcrPdfParser(BaseParser):
    """扫描件 PDF 走 OCR 的兜底解析器（不注册同名）。

    调用方应先跑 PdfParser，检测文字层 <50 字时再调用本类。
    """

    supported_ext = ".pdf.ocr"

    def extract(self, file_bytes: bytes) -> str:
        try:
            import pytesseract
            from PIL import Image
        except ImportError as e:
            raise RuntimeError(f"OCR 依赖缺失: {e}")

        pages = _pdf_pages_to_images(file_bytes)
        if not pages:
            return ""

        parts = []
        for i, png in enumerate(pages):
            img = Image.open(io.BytesIO(png))
            text = pytesseract.image_to_string(img, lang="chi_sim+eng")
            if text.strip():
                parts.append(f"=== 第{i+1}页 ===\n{text.strip()}")
        return "\n\n".join(parts)


def smart_parse_pdf(file_bytes: bytes, fallback_ocr: bool = True) -> tuple[str, str]:
    """PDF 智能解析：先文字层，空则 OCR。返回 (text, method)。

    method: "text" | "ocr" | "empty"
    """
    from parsers.pdf_parser import PdfParser

    text = PdfParser().extract(file_bytes)
    if len(text.strip()) >= 50 or not fallback_ocr:
        return text, "text"

    # OCR fallback
    try:
        ocr = OcrPdfParser()
        ocr_text = ocr.extract(file_bytes)
        if ocr_text.strip():
            return ocr_text, "ocr"
    except RuntimeError as e:
        return text, f"text+ocr_unavailable({e})"
    return text, "empty"
