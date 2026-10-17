"""装备 PDF → 本体对齐三元组 抽取模块（v2 本体对齐版）。

被 Flask UI 和命令行脚本共同调用。所有输出三元组必须通过
ontology.validate_triple(head_code, rel_en, tail_code) 校验，
确保 domain→range 约束满足。

核心输出格式:
    {
        "head": "DNBSEQ-E25RS基因测序仪",
        "hl":   "E01-01 生物侦检装备",    # code + name_zh
        "head_code": "E01-01",             # 用于 Neo4j label 生成
        "rel":  "adopts",                  # 本体关系英文名
        "tail": "联合探针锚定聚合(cPAS)测序技术",
        "tl":   "E03-01 装备原理",
        "tail_code": "E03-01",
        "evidence": "工作原理章节第X段"     # 可选，溯源用
    }

本体来源: ontology.py (56 实体 + 20 关系 + 101 属性)
"""
from __future__ import annotations

import io
import os
import re
from collections import Counter
from typing import Optional

from ontology import (
    ENTITY_TYPES, RELATION_TYPES, ATTRIBUTE_KEYS,
    validate_triple as ontology_validate,
    EntityDef, RelationDef,
)


# ============================================================
# 装备分类 → 本体 E01-xx code 映射
# ============================================================
_EQUIPMENT_CLASSIFY = [
    # --- E01-01 生物侦检装备（最具体，放最前）---
    (["测序仪", "基因测序", "测序芯片", "Flow Cell", "DNBSEQ", "单[Bb]arcode", "双[Bb]arcode"], "E01-01", "生物侦检装备"),
    (["POCT", "即时检测", "核酸检测"], "E01-01", "生物侦检装备"),

    # --- E01-04 检验检测与采样装备 ---
    (["酶标仪", "酶标", "微孔板检测仪", "全波长"], "E01-04", "检验检测与采样装备"),
    (["扫描电镜", "电镜", "SEM", "显微镜"], "E01-04", "检验检测与采样装备"),
    (["荧光计", "荧光光谱", "分光光度计", "光谱仪"], "E01-04", "检验检测与采样装备"),
    (["PCR仪", "荧光定量PCR", "实时荧光", "胶体金"], "E01-04", "检验检测与采样装备"),
    (["检测", "采样", "检验"], "E01-04", "检验检测与采样装备"),

    # --- E01-02 消毒灭菌装备 ---
    (["喷雾器", "消杀", "消毒", "灭菌", "烟雾机", "超低容量", "气溶胶"], "E01-02", "消毒灭菌装备"),

    # --- E01-03 个体防护装备 ---
    (["防护服", "口罩", "呼吸器", "过滤", "防护等级", "气密性"], "E01-03", "个体防护装备"),

    # --- E01-05 医疗救护与预防用药装备 ---
    (["急救", "呼吸机", "接种", "疫苗", "药品储运"], "E01-05", "医疗救护与预防用药装备"),

    # --- E01-06 通信指挥与信息装备 ---
    (["通信", "指挥", "对讲机", "无线", "信息处理"], "E01-06", "通信指挥与信息装备"),

    # --- E01-07 运输投送与携行装备 ---
    (["转运", "运输", "携行", "急救车", "方舱", "冰柜", "冰箱", "冷藏", "车载"], "E01-07", "运输投送与携行装备"),

    # --- E01-08 后勤保障与环境卫生装备 ---
    (["帐篷", "卫生设施", "废弃物", "后勤"], "E01-08", "后勤保障与环境卫生装备"),

    # --- 兜底 ---
    (["分析仪", "检测仪", "分析"], "E01-04", "检验检测与采样装备"),
]


def classify_equipment(text: str, filename: str = "") -> tuple[str, str]:
    """判断装备属于 E01 下哪个二级子类。

    Returns: (code, name_zh)  e.g. ("E01-01", "生物侦检装备")
    """
    search = (filename + " " + text[:3000]).lower()
    for keywords, code, name in _EQUIPMENT_CLASSIFY:
        if any(kw.lower() in search for kw in keywords):
            return code, name
    return "E01-04", "检验检测与采样装备"  # 默认兜底改为 E01-04


# ============================================================
# Neo4j label 生成
# ============================================================
def code_to_neo4j_label(code: str) -> str:
    """概念类 code → Neo4j label（下划线连字符）。"""
    return code.replace("-", "_")


def code_to_display(code: str) -> str:
    """概念类 code → "code name_zh" 格式（用于 hl/tl 字段）。"""
    e = ENTITY_TYPES.get(code)
    if e:
        return f"{e.code} {e.name_zh}"
    return code


# ============================================================
# 抽取模式定义（全部对齐本体）
# ============================================================

# --- E02-03 装备部件（可被 matchedWith 关系匹配）---
# 这些部件属于装备的"组成部分"，是 matchedWith 的尾实体
_COMPONENT_PATTERNS = [
    # 核心模块/单元
    r"(控制单元|测序单元|光学检测系统|电源模块|数据处理单元|主板|计算模块|主机)",
    # 显示/操作
    r"(显示屏|触摸屏|显示模块|操作面板|键盘|打印机|指示灯)",
    # 采样/反应
    r"(芯片槽|样本槽|试剂槽|样本架|试剂架|测序芯片|反应杯|样品杯|Flow Cell)",
    # 流体/气体
    r"(管路|阀门|泵|废液瓶|缓冲液|清洗液|清洗管路)",
    # 温控/环境
    r"(冷却系统|加热系统|温控模块|气体供应|液体供应)",
    # 光学/电子/机械
    r"(光路系统|电子系统|机械系统|外壳|面板|盖板)",
    # 连接/接口
    r"(USB[0-9]?|LAN|串口|以太网接口|数据接口|电源线|数据线|适配器)",
    # 电源
    r"(电池|UPS电源|电源适配器|输入电源|电源模块)",
    # 其他
    r"(开关|旋钮|扫码枪|冰箱|冰柜|低温保存|风扇|过滤器)",
]

# --- E03-01 装备原理（adopts 关系的尾实体）---
_TECH_PATTERNS = [
    r"((?:联合探针锚定聚合|cPAS)[\(\)（）]?[^，。；\n]{0,30}测序技术?)",
    r"((?:DNA纳米球|DNB)[\(\)（）]?[^，。；\n]{0,20}技术?)",
    r"((?:微流控[集成式]?)[^，。；\n]{0,20}(?:载片|芯片|系统))",
    r"((?:滚环扩增|滚环复制|RCA)[\(\)（）]?[^，。；\n]{0,15}(?:技术|原理|法))",
    r"(自发光测序生化体系)",
    r"(边合成边测序\[|SBS\][^，。；\n]{0,15}方法?)",
    r"(单分子实时测序\[|SMRT\][^，。；\n]{0,15}技术?)",
    r"(纳米孔测序[^，。；\n]{0,15}技术?)",
    r"(半导体测序[^，。；\n]{0,15}技术?)",
]

# --- E14-02 技术标准（basedOn 关系的尾实体）---
_STANDARD_PATTERNS = [
    r"(GB/T?\s*\d[\d\.\-]+\s*[\u4e00-\u9fa5A-Za-z0-9\-]{2,40})",
    r"(SJ/T\s*\d[\d\.\-]+\s*[\u4e00-\u9fa5A-Za-z0-9\-]{2,30})",
    r"(YY/T\s*\d[\d\.\-]+\s*[\u4e00-\u9fa5A-Za-z0-9\-]{2,30})",
    r"(QC/T\s*\d[\d\.\-]+\s*[\u4e00-\u9fa5A-Za-z0-9\-]{2,30})",
    r"(ISO\s*\d[\d\.\-]+\s*[\u4e00-\u9fa5A-Za-z0-9\-]{2,30})",
    r"(IEC\s*\d[\d\.\-]+\s*[\u4e00-\u9fa5A-Za-z0-9\-]{2,30})",
]

# --- E13-01 作业能力（has 关系的尾实体，描述装备能做什么）---
_CAPABILITY_PATTERNS = [
    r"((?:生信分析|生物信息|数据分析)[^，。；\n]{0,10}能力)",
    r"((?:高通量|高深度|大规模)[^，。；\n]{0,10}(?:测序|检测|分析))",
    r"((?:单[Bb]arcode|双[Bb]arcode)[^，。；\n]{0,15}测序)",
    r"((?:长读长|短读长)[^，。；\n]{0,10}(?:测序|分析))",
    r"((?:多重|多通道|荧光)[^，。；\n]{0,10}(?:检测|分析))",
]

# --- 故障 + 部件联动（FAULT_WORDS 必须配合 COMPONENT_PATTERNS 才算真实故障）---
_FAULT_WORDS = ["故障", "失效", "异常", "无法", "不能", "不识别", "不工作", "不启动",
                "死机", "黑屏", "无信号", "无数据", "报警", "提示", "警告",
                r"E-\d+", r"F-\d+", r"ERR-\d+"]

# --- 101 属性抽取模式（覆盖 AT-001~AT-101）---
# 每个属性 key: (中文关键词列表, 正则模式, AT-xxx code)
# 匹配成功后 tail 格式 = "属性名=值"，tl = "E13-02 性能指标"（has 关系）
_ATTRIBUTE_PATTERNS: list[tuple[list[str], str, str]] = [
    # --- 基础属性 ---
    (["装备名称", "产品名称"], r"(?:产品名称|装备名称)[：:]\s*([^\n，。；]{2,40})", "AT-001"),
    (["装备编号", "产品编号"], r"(?:装备编号|产品编号|编号)[：:]\s*([^\n，。；]{2,20})", "AT-002"),
    (["装备类别", "产品类别"], r"(?:装备类别|产品类别|分类)[：:]\s*([^\n，。；]{2,20})", "AT-003"),
    (["型号"], r"(?:型号|规格型号)[：:]\s*([\w\-&]+)", "AT-003"),  # 型号 → 类别

    # --- 厂家 ---
    (["研制单位", "研制"], r"研制[单位]?[：:]\s*([^\n，。；]{2,30})", "AT-004"),
    (["生产厂家", "厂家", "制造商"], r"(?:生产厂家|制造商|厂家|出品)[：:]\s*([^\n，。；]{2,30})", "AT-005"),

    # --- 物理参数 ---
    (["外形尺寸", "体积", "尺寸"], r"(?:外形尺寸|体积|尺寸)[：:]\s*([0-9.]+\s*[×xX*]\s*[0-9.]+\s*[×xX*]\s*[0-9.]+\s*\w*)", "AT-018"),
    (["重量", "净重", "质量"], r"(?:主机净重|净重|整备质量|重量)[：:]?\s*([0-9.~]+\s*\w+)", "AT-019"),

    # --- 环境要求 ---
    (["工作温度", "操作温度"], r"(?:工作温度|操作温度|使用温度)[：:]\s*([0-9\-~.]+°?C?\s*[至~到]\s*[0-9\-~.]+°?C?)", "AT-020"),
    (["相对湿度", "湿度"], r"(?:操作相对湿度|相对湿度|环境湿度)[：:]\s*([0-9\-~.]+%?\s*[至~到]\s*[0-9\-~.]+%?\s*RH?)", "AT-038"),
    (["大气压力", "气压"], r"(?:大气压力|气压范围)[：:]\s*([0-9\-~.]+\s*[kK][pP][aA]?)", "AT-039"),
    (["防雨密封", "防护等级", "IP"], r"(?:防雨密封|外壳防护|防护等级)[：:]\s*([Ii][Pp]\d+)", "AT-021"),
    (["运输储存温度", "储运温度"], r"(?:运输[／/]储存温度|储运温度)[：:]\s*([0-9\-~.]+°?C?\s*[至~到]\s*[0-9\-~.]+°?C?)", "AT-043"),

    # --- 电源 ---
    (["输入电源", "电源输入"], r"(?:主机输入电源|计算模块电源|输入电源)[：:]\s*([^\n，。；]{2,30})", "AT-041"),
    (["额定功率", "功率", "功耗"], r"(?:额定功率|最大功率|功耗|功率)[：:]\s*([0-9.]+\s*\w+)", "AT-055"),

    # --- 测序仪专属 ---
    (["触摸屏", "显示屏"], r"(?:触摸屏|显示模块)[：:]?\s*([^\n，。；]{2,30})", "AT-037"),
    (["占桌面积", "占地"], r"(?:占桌面积|占地面积)[：:]\s*([0-9.]+\s*[×xX*]\s*[0-9.]+\s*\w*)", "AT-046"),
    (["单次运行数据量", "数据量", "输出数据"], r"(?:单次运行数据量|输出数据量|数据输出)[：:]\s*([^\n，。；]{2,20})", "AT-047"),
    (["单次运行Reads", "Reads"], r"(?:单次运行Reads数|Reads数|reads)[：:]\s*([0-9.]+\s*[MmGg])", "AT-048"),
    (["测序时间"], r"(?:测序时间|测序速度)[：:]\s*([^\n，。；]{2,20})", "AT-049"),
    (["Q30"], r"(?:Q30|质量值)[：:]\s*([0-9.]+\s*%?)", "AT-050"),
    (["加载方式", "上样"], r"(?:加载方式|上样方式|样本加载)[：:]\s*([^\n，。；]{2,20})", "AT-051"),
    (["样本通量", "通量"], r"(?:样本通量|样本量通量)[：:]\s*([^\n，。；]{2,20})", "AT-052"),
    (["荧光通道", "荧光靶标"], r"(?:荧光通道|荧光通道数|荧光靶标)[：:]\s*([^\n，。；]{2,20})", "AT-053"),
    (["空气过滤", "HEPA"], r"(?:空气过滤|HEPA)[：:]\s*([^\n，。；]{2,15})", "AT-057"),
    (["使用寿命", "使用期限"], r"(?:使用寿命|使用期限|设计寿命)[：:]\s*([0-9.]+\s*年)", "AT-025"),
    (["最大声压级", "噪声"], r"(?:最大声压级|工作噪声)[：:]\s*([^\n，。；]{2,15})", "AT-044"),
    (["软件配置", "软件"], r"(?:软件配置|配套软件|系统软件)[：:]\s*([^\n，。；]{2,30})", "AT-045"),
    (["操作系统"], r"操作系统[：:]\s*([^\n，。；]{2,20})", "AT-099"),
    (["计算模块净重"], r"计算模块净重[约]?\s*([0-9.]+\s*\w+)", "AT-101"),
    (["主机净重"], r"主机净重[约]?\s*([0-9.]+\s*\w+)", "AT-100"),

    # --- 酶标仪专属 ---
    (["波长范围", "波长"], r"(?:波长范围-?光吸收|波长范围-?荧光|波长范围-?化学发光|波长范围)[：:]\s*([0-9.~]+\s*\w+\s*[至~到]\s*[0-9.~]+\s*\w*)", "AT-065"),
    (["温度控制", "温控"], r"(?:温度控制范围|温控范围)[：:]\s*([0-9.~]+°?C?\s*[至~到±]+\s*[0-9.~]+°?C?)", "AT-071"),
    (["检测限", "灵敏度"], r"(?:检测限|灵敏度)[：:]\s*([^\n，。；]{2,20})", "AT-015"),
    (["检测时间", "检出时间"], r"(?:检测时间|检出时间)[：:]\s*([0-9.]+\s*\w+)", "AT-016"),
    (["检测靶标", "靶标"], r"(?:检测靶标|靶标)[：:]\s*([^\n，。；]{2,30})", "AT-017"),
    (["波长范围-光吸收"], r"光吸收波长范围[：:]?\s*([0-9.~]+\s*[至~到]\s*[0-9.~]+\s*\w*)", "AT-065"),
    (["波长范围-荧光"], r"荧光波长范围[：:]?\s*([0-9.~]+\s*[至~到]\s*[0-9.~]+\s*\w*)", "AT-066"),
    (["波长范围-化学发光"], r"化学发光波长范围[：:]?\s*([0-9.~]+\s*[至~到]\s*[0-9.~]+\s*\w*)", "AT-067"),
    (["带宽"], r"带宽[：:]\s*([^\n，。；]{2,15})", "AT-068"),
    (["光吸收检测范围", "OD值"], r"(?:光吸收检测范围|OD值范围)[：:]\s*([0-9.~]+\s*[至~到]\s*[0-9.~]+\s*\w*)", "AT-069"),
    (["荧光动态范围"], r"荧光动态范围[：:]\s*([^\n，。；]{2,20})", "AT-070"),
    (["芯片通道"], r"芯片样本通道数[：:]\s*([0-9]+)", "AT-058"),
    (["建库时间"], r"建库时间[：:]\s*([0-9.]+\s*\w+)", "AT-060"),
    (["样本类型"], r"样本类型[：:]\s*([^\n，。；]{2,30})", "AT-063"),
    (["配套软件", "分析软件"], r"(?:配套软件|分析软件)[：:]\s*([^\n，。；]{2,25})", "AT-072"),
    (["功率", "电源"], r"(?:电源|电源要求)[：:]\s*([^\n，。；]{2,20})", "AT-088"),

    # --- 扫描电镜专属 ---
    (["放大倍数", "放大倍率"], r"(?:放大倍数|放大倍率|放大)[：:]\s*([0-9.~]+\s*×?\s*[至~到]\s*[0-9.~]+\s*×)", "AT-073"),
    (["加速电压"], r"加速电压[：:]\s*([0-9.~]+\s*\w+\s*[至~到]\s*[0-9.~]+\s*\w*)", "AT-074"),
    (["抽真空时间"], r"抽真空时间[：:]\s*([^\n，。；]{2,15})", "AT-075"),
    (["低真空", "真空范围"], r"(?:低真空范围|真空范围)[：:]\s*([^\n，。；]{2,20})", "AT-076"),
    (["最大样品尺寸", "样品尺寸"], r"(?:最大样品尺寸|样品尺寸)[：:]\s*([^\n，。；]{2,20})", "AT-078"),
    (["样品台行程", "样品台"], r"样品台行程[：:]\s*([^\n，。；]{2,25})", "AT-079"),
    (["成像模式", "成像"], r"成像模式[：:]\s*([^\n，。；]{2,20})", "AT-080"),
    (["信号采集带宽"], r"信号采集带宽[：:]\s*([^\n，。；]{2,15})", "AT-077"),

    # --- 荧光计专属 ---
    (["检测浓度", "浓度范围"], r"(?:检测浓度范围|浓度范围)[：:]\s*([^\n，。；]{2,25})", "AT-081"),
    (["样本量"], r"(?:样本量|上样量)[：:]\s*([^\n，。；]{2,20})", "AT-083"),
    (["光程"], r"光程[：:]\s*([^\n，。；]{2,15})", "AT-084"),
    (["加热温度", "孵育温度"], r"(?:加热温度|孵育温度)[：:]\s*([0-9.~]+\s*°?C?\s*[至~到±]+\s*[0-9.~]+\s*°?C?)", "AT-085"),
    (["搅拌速度"], r"搅拌速度[：:]\s*([0-9.]+\s*\w+)", "AT-086"),
    (["光源寿命"], r"光源寿命[：:]\s*([0-9.]+\s*\w+)", "AT-087"),
]


# ============================================================
# PDF 读取
# ============================================================
def read_pdf(pdf_path: str) -> str:
    import fitz
    doc = fitz.open(pdf_path)
    text = "\n".join(doc[p].get_text() for p in range(doc.page_count))
    doc.close()
    return text


def read_pdf_from_bytes(data: bytes, filename: str = "upload.pdf") -> str:
    """从内存 bytes 读 PDF（Flask 上传场景）"""
    import fitz
    doc = fitz.open(stream=io.BytesIO(data), filetype="pdf")
    text = "\n".join(doc[p].get_text() for p in range(doc.page_count))
    doc.close()
    return text


# ============================================================
# 装备名识别
# ============================================================
def detect_equipment_name(text: str, filename: str = "") -> str:
    """从 PDF 首页提取装备型号，退化到文件名清理"""
    first_page_text = text[:3000]
    # 1. 显式型号字段
    m = re.search(r"(?:型号|产品型号|规格型号)[：:]\s*([\w\-&]+)", first_page_text)
    if m:
        return m.group(1)
    # 2. 大厂型号前缀
    m = re.search(r"(DNBSEQ[-A-Z0-9&]+|MF[-A-Z0-9&]*|Fluo[-A-Z0-9&]*|iScanner[-A-Z0-9&]*)", first_page_text)
    if m:
        return m.group(1)
    # 3. 退化到文件名清理
    base = os.path.basename(filename).replace(".pdf", "").replace("_saved", "")
    base = re.sub(r"^[\(\[无水印\)\]]*\d*[-－]\s*", "", base)
    return base or "未知装备"


# ============================================================
# 核心抽取（本体对齐版）
# ============================================================
def _make_triple(
    head: str, head_code: str,
    rel_en: str,
    tail: str, tail_code: str,
    validate: bool = True,
) -> Optional[dict]:
    """构造一条本体对齐的三元组，自动校验 domain→range 约束。

    Returns: dict 或 None（校验不通过时丢弃）
    """
    if validate and not ontology_validate(head_code, rel_en, tail_code):
        return None

    rel_def = RELATION_TYPES.get(next((k for k, v in RELATION_TYPES.items() if v.name_en == rel_en), ""))
    rel_code = rel_def.code if rel_def else "R-???"

    return {
        "head": head.strip(),
        "hl": code_to_display(head_code),
        "head_code": head_code,
        "rel": rel_en,
        "rel_code": rel_code,
        "tail": tail.strip(),
        "tl": code_to_display(tail_code),
        "tail_code": tail_code,
    }


def extract_from_text(
    text: str,
    equipment_name: str,
    equipment_code: str = "",
) -> list[dict]:
    """从单个装备 PDF 文本抽取本体对齐的三元组。

    Args:
        text: PDF 全文
        equipment_name: 装备型号（如 "DNBSEQ-E25RS基因测序仪"）
        equipment_code: 本体概念类 code（如 "E01-01"），不传则自动识别
    """
    if not equipment_code:
        equipment_code, _ = classify_equipment(text)

    triples: list[dict] = []
    seen = set()

    def _add(trip: Optional[dict]):
        if trip:
            k = (trip["head"], trip["rel"], trip["tail"])
            if k not in seen:
                seen.add(k)
                triples.append(trip)

    # ============ 1. E01 → E02-03 matchedWith 装备部件 ============
    seen_comps = set()
    for pat in _COMPONENT_PATTERNS:
        for m in re.finditer(pat, text):
            comp = m.group(1).strip()
            if comp and comp not in seen_comps and 2 <= len(comp) <= 20:
                seen_comps.add(comp)
                _add(_make_triple(
                    equipment_name, equipment_code,
                    "matchedWith",
                    comp, "E02-03",
                ))

    # ============ 2. E01 → E03-01 adopts 装备原理/技术 ============
    seen_techs = set()
    for pat in _TECH_PATTERNS:
        for m in re.finditer(pat, text):
            tech = m.group(1).strip()
            if tech and tech not in seen_techs and len(tech) >= 4:
                seen_techs.add(tech)
                _add(_make_triple(
                    equipment_name, equipment_code,
                    "adopts",
                    tech, "E03-01",
                ))

    # ============ 3. E01 → E14-02 basedOn 技术标准 ============
    seen_stds = set()
    for pat in _STANDARD_PATTERNS:
        for m in re.finditer(pat, text):
            std = m.group(1).strip()
            if std and std not in seen_stds and len(std) >= 8:
                seen_stds.add(std)
                _add(_make_triple(
                    equipment_name, equipment_code,
                    "basedOn",
                    std, "E14-02",
                ))

    # ============ 4. E01 → E13-01 has 作业能力 ============
    seen_caps = set()
    for pat in _CAPABILITY_PATTERNS:
        for m in re.finditer(pat, text):
            cap = m.group(1).strip()
            if cap and cap not in seen_caps and len(cap) >= 4:
                seen_caps.add(cap)
                _add(_make_triple(
                    equipment_name, equipment_code,
                    "has",
                    cap, "E13-01",
                ))

    # ============ 5. E01 → E13-02 has 性能指标（101 属性）============
    seen_attrs = set()
    for keywords, pat, attr_code in _ATTRIBUTE_PATTERNS:
        for m in re.finditer(pat, text):
            val = m.group(1).strip()
            if not val or len(val) > 60:
                continue
            # 检查属性名关键词是否真的出现在附近（排除误匹配）
            context_start = max(0, m.start() - 50)
            context = text[context_start:m.end() + 10]
            if not any(kw in context for kw in keywords):
                continue
            # 属性名：从正则里的中文关键词取第一个
            attr_name = keywords[0]
            key = f"{attr_code}={val}"
            if key in seen_attrs:
                continue
            seen_attrs.add(key)
            tail = f"{attr_name}={val}"
            _add(_make_triple(
                equipment_name, equipment_code,
                "has",
                tail, "E13-02",
            ))

    # ============ 6. E01 → E07-01 performsTask 执行任务 ============
    task_pats = [
        (r"(?:可用于|用于|支持|实现|能够)\s*([^，。；\n]{4,30})", "E07-01"),
        (r"(?:主要功能|功能)[：:]\s*([^，。；\n]{4,40})", "E07-01"),
    ]
    for pat, tail_code in task_pats:
        for m in re.finditer(pat, text):
            task = m.group(1).strip()
            if 4 <= len(task) <= 40:
                _add(_make_triple(
                    equipment_name, equipment_code,
                    "performsTask",
                    task, tail_code,
                ))

    # ============ 7. E01 → E09 applicableTo 适用于场所 ============
    venue_pats = [
        r"(?:适用于|可在)[：:]?\s*([^，。；\n]{4,20})",
        r"(?:在|用于)\s*([^，。；\n]{4,15}(?:实验室|现场|灾区|战场|医院))",
    ]
    for pat in venue_pats:
        for m in re.finditer(pat, text):
            venue = m.group(1).strip()
            if 4 <= len(venue) <= 20:
                _add(_make_triple(
                    equipment_name, equipment_code,
                    "applicableTo",
                    venue, "E09",
                ))

    # ============ 9. E01 → E11 targets 针对病原体/媒介生物 ============
    # R-008 targets: domain=E01/E12, range=E11-02/E11-03
    pathogen_pats = [
        r"((?:针对|检测|识别|鉴别|筛检)[^，。；\n]{0,5}(?:病原微生物|病原体|病毒|细菌|真菌|立克次体|寄生虫))",
        r"((?:检测|定量|定性)[^，。；\n]{0,5}(?:样本|样品)[^，。；\n]{0,5}(?:中|的)?(?:病毒|细菌|真菌|核酸|DNA|RNA))",
        r"(?:靶标|检测靶标)[：:]?\s*([^，。；\n]{2,40}(?:病毒|细菌|核酸|病原体))",
    ]
    for pat in pathogen_pats:
        for m in re.finditer(pat, text):
            target = m.group(1).strip()
            if 4 <= len(target) <= 40:
                _add(_make_triple(
                    equipment_name, equipment_code,
                    "targets",
                    target, "E11-02",
                ))

    # ============ 10. E01 → E12 uses 使用试剂耗材 ============
    # R-006 uses: domain=E08/E08-01, range=E01 —— 但 E01→E12 也合理（装备用什么试剂）
    # 这里用 matchedWith 不行（domain/range 不匹配），改用 has 也可以
    # 但 uses 的 domain 是 E08（人/组织），不是 E01（装备）
    # 所以装备→试剂 用 matchedWith 不行，用 has 也不行（has range=E03/E13/E02）
    # 装备→配套试剂 用 hasPart 也不合适
    # 结论：用 matchedWith 扩展 range 到 E12（装备配套药剂耗材是合理的）
    # 但当前 ontology.py 的 R-002 matchedWith range 已包含 E12 ✅
    reagent_pats = [
        r"((?:使用|配套|需用)[^，。；\n]{0,5}(?:试剂|试剂盒|检测试剂|耗材|反应液|缓冲液))",
        r"((?:试剂|试剂盒)[：:]\s*([^，。；\n]{2,30}))",
    ]
    for pat in reagent_pats:
        for m in re.finditer(pat, text):
            reagent = m.group(1).strip()
            if 4 <= len(reagent) <= 40:
                _add(_make_triple(
                    equipment_name, equipment_code,
                    "matchedWith",  # R-002 range 已包含 E12
                    reagent, "E12",
                ))

    # ============ 8. 故障识别（FAULT_WORDS + 部件联动过滤）============
    # 必须同时包含 FAULT_WORDS 和 COMPONENT_PATTERNS 才算真实故障
    fault_component_names = set()
    for pat in _COMPONENT_PATTERNS:
        for m in re.finditer(pat, text):
            fault_component_names.add(m.group(1).strip())

    sentences = re.split(r"[。！？\n]", text)
    for sent in sentences:
        sent = sent.strip()
        if not (5 <= len(sent) <= 150):
            continue
        if not any(re.search(fw, sent) for fw in _FAULT_WORDS):
            continue
        # 关键：必须包含至少一个已知部件名才认定为真实故障
        has_component = any(c in sent for c in fault_component_names)
        if not has_component:
            continue
        fault_desc = sent[:80]
        _add(_make_triple(
            equipment_name, equipment_code,
            "hasPart",  # 临时占位，Fault 的本体 code 需确认
            fault_desc, "E04-03",  # E04-03 装备维修（故障属于维修范畴）
        ))

    return triples


def extract_from_pdf(pdf_path: str) -> dict:
    """一键从 PDF 文件抽取：返回 {equipment, triples, text_len, is_scanned, equipment_code}"""
    text = read_pdf(pdf_path)
    equipment_name = detect_equipment_name(text, pdf_path)
    equipment_code, equipment_class = classify_equipment(text, pdf_path)
    triples = extract_from_text(text, equipment_name, equipment_code)
    return {
        "equipment": equipment_name,
        "equipment_class": equipment_class,
        "equipment_code": equipment_code,
        "triples": triples,
        "text_len": len(text),
        "is_scanned": len(text) < 50,
    }


# ============================================================
# Neo4j MERGE（本体对齐版）
# ============================================================
def merge_triples(driver, triples: list[dict]) -> dict:
    """把本体对齐的三元组 MERGE 进 Neo4j。

    - 节点 label: E01_01 / E02_03 等（ontology code → 下划线）
    - 关系类型: adopts / matchedWith / has 等（本体英文名）
    - 额外 label: 自动加上所有祖先（E01_01 同时打 E01 和 E00 标签）
    - MERGE 键: (code, name) —— 同类型同名字才合并

    Returns: {added_nodes, added_rels, total, skipped}
    """
    from ontology import ENTITY_TYPES, code_to_neo4j_label

    added_nodes = 0
    added_rels = 0
    skipped = 0

    with driver.session() as s:
        for t in triples:
            head_code = t.get("head_code", "")
            tail_code = t.get("tail_code", "")
            rel = t["rel"]
            head_name = t["head"]
            tail_name = t["tail"]

            # 构造 Neo4j label（自身 + 所有祖先）
            head_labels = _all_labels(head_code)
            tail_labels = _all_labels(tail_code)
            head_label_str = ":".join(head_labels)
            tail_label_str = ":".join(tail_labels)

            # MERGE 节点（code + name 作为唯一键）
            r_a = s.run(
                f"MERGE (a:{head_label_str} {{code: $code, name: $name}}) "
                f"RETURN count(DISTINCT a) AS c",
                code=head_code, name=head_name,
            ).single()
            if r_a["c"] > 0:
                added_nodes += 1

            r_b = s.run(
                f"MERGE (b:{tail_label_str} {{code: $code, name: $name}}) "
                f"RETURN count(DISTINCT b) AS c",
                code=tail_code, name=tail_name,
            ).single()
            if r_b["c"] > 0:
                added_nodes += 1

            # MERGE 关系
            try:
                r_r = s.run(
                    f"MATCH (a:{head_label_str} {{code: $hc, name: $hn}}), "
                    f"(b:{tail_label_str} {{code: $tc, name: $tn}}) "
                    f"MERGE (a)-[r:{rel}]->(b) "
                    f"RETURN count(r) AS c",
                    hc=head_code, hn=head_name,
                    tc=tail_code, tn=tail_name,
                ).single()
                if r_r["c"] == 0:
                    added_rels += 1
            except Exception as e:
                print(f"  ⚠ MERGE 关系失败 [{rel}]: {e}")
                skipped += 1

    return {"added_nodes": added_nodes, "added_rels": added_rels,
            "total": len(triples), "skipped": skipped}


def _all_labels(code: str) -> list[str]:
    """返回某概念类在 Neo4j 中应该打的所有 label（自身 + 所有祖先）。"""
    from ontology import ENTITY_TYPES
    labels = []
    e = ENTITY_TYPES.get(code)
    while e:
        labels.append(e.neo4j_label)
        e = ENTITY_TYPES.get(e.parent) if e.parent else None
    return labels
