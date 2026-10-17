"""OCR 解析器 — 扫描件 PDF / 图片。

环境要求（已就绪）:
  1. Tesseract 本体: C:\\Program Files\\Tesseract-OCR\\tesseract.exe (5.4.0)
  2. Python 绑定: pytesseract + pillow (清华镜像已装)
  3. 语言包: eqkg-poc/tessdata/ (chi_sim + eng + osd)

用法：当 PdfParser 返回空串时，调用方自动 fallback 到 OcrPdfParser，
或直接调 smart_parse_pdf(bytes) 一步到位。
"""
from __future__ import annotations

import io
import os
from pathlib import Path

from parsers.base import BaseParser, register_parser, logger

# ===== Tesseract 定位 =====
_TESSERACT_CANDIDATES = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
]

# 本地 tessdata（chi_sim/eng/osd），与项目同级
_TESSDATA_DIR = Path(__file__).resolve().parent.parent / "tessdata"


def _find_tesseract() -> str | None:
    """按候选路径找 tesseract.exe，PATH 优先。"""
    import shutil
    which = shutil.which("tesseract")
    if which:
        return which
    for p in _TESSERACT_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


def _configure_pytesseract() -> "tuple[str, str]":
    """返回 (tesseract_cmd, tessdata_dir)，找不到时抛 RuntimeError。

    同时设置 TESSDATA_PREFIX 环境变量指向本地 tessdata
    （Tesseract 4/5 语义：直接指向包含 traineddata 的目录），
    子进程会继承该变量。
    """
    cmd = _find_tesseract()
    if not cmd:
        raise RuntimeError(
            "Tesseract 未找到。请安装: winget install UB-Mannheim.TesseractOCR"
        )
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = cmd
    os.environ["TESSDATA_PREFIX"] = str(_TESSDATA_DIR)
    return cmd, str(_TESSDATA_DIR)


# OCR 语言配置（中文简体 + 英文）
_OCR_LANG = "chi_sim+eng"


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
            raise RuntimeError(f"OCR 依赖缺失: {e}. 请: py -3.12 -m pip install pytesseract pillow")

        cmd, tessdata_dir = _configure_pytesseract()
        img = Image.open(io.BytesIO(file_bytes))
        return pytesseract.image_to_string(img, lang=_OCR_LANG)


def _pdf_pages_to_images(pdf_bytes: bytes, max_pages: int = 30, dpi: int = 200) -> list[bytes]:
    """把 PDF 每页渲染成 PNG bytes（OCR 输入）。"""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return []
    doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
    try:
        results = []
        for page_num in range(min(doc.page_count, max_pages)):  # 上限防止 OCR 卡爆
            page = doc[page_num]
            pix = page.get_pixmap(dpi=dpi)
            results.append(pix.tobytes("png"))
        return results
    finally:
        doc.close()


class OcrPdfParser(BaseParser):
    """扫描件 PDF 走 OCR 的兜底解析器（不注册同名）。

    调用方应先跑 PdfParser，检测文字层 <50 字时再调用本类。
    """

    supported_ext = ".pdf.ocr"

    def __init__(self, dpi: int = 200, max_pages: int = 30):
        self.dpi = dpi
        self.max_pages = max_pages

    def extract(self, file_bytes: bytes) -> str:
        try:
            import pytesseract
            from PIL import Image
        except ImportError as e:
            raise RuntimeError(f"OCR 依赖缺失: {e}")

        cmd, tessdata_dir = _configure_pytesseract()
        pages = _pdf_pages_to_images(file_bytes, max_pages=self.max_pages, dpi=self.dpi)
        if not pages:
            return ""

        parts = []
        for i, png in enumerate(pages):
            img = Image.open(io.BytesIO(png))
            text = pytesseract.image_to_string(img, lang=_OCR_LANG)
            if text.strip():
                parts.append(text.strip())
        return "\n".join(parts)


def smart_parse_pdf(file_bytes: bytes, fallback_ocr: bool = True) -> tuple[str, str]:
    """PDF 智能解析：先文字层，空则 OCR。返回 (text, method)。

    method: "text" | "ocr" | "empty" | "text+ocr_unavailable(...)"
    """
    from parsers.pdf_parser import PdfParser

    text = PdfParser().extract(file_bytes)
    if len(text.strip()) >= 50 or not fallback_ocr:
        return text, "text"

    # OCR fallback
    try:
        ocr_text = OcrPdfParser().extract(file_bytes)
        if ocr_text.strip():
            return ocr_text, "ocr"
    except RuntimeError as e:
        logger.warning(f"[OCR] 不可用: {e}")
        return text, f"text+ocr_unavailable({e})"
    return text, "empty"
