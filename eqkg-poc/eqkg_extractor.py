"""
装备 PDF → 知识图谱三元组 抽取模块
被 Flask UI 和命令行脚本共同调用。

核心函数:
  read_pdf(path)                     → str (从文件路径读)
  read_pdf_from_bytes(data, name)    → str (从内存 bytes 读, Flask 上传用)
  detect_equipment_name(text, fname) → str (识别装备型号)
  extract_from_text(text, equip)     → list[triple]
  extract_from_pdf(path)             → dict(equipment, triples, text_len)
"""
import io, os, re
import fitz  # PyMuPDF

# ===== 规则定义（与 rule-extract-real-pdfs.py 保持一致）=====
COMPONENT_PATTERNS = [
    r"(控制单元|测序单元|光学检测系统|电源模块|数据处理单元|主板|显示屏|触摸屏|键盘|打印机|传感器|"
    r"芯片槽|样本槽|试剂槽|管路|阀门|泵|电机|冷却系统|加热系统|温控模块|气体供应|液体供应|"
    r"光路系统|电子系统|机械系统|系统软件|固件|接口|USB|LAN|串口|电池|适配器|电源线|数据线|"
    r"外壳|面板|盖板|旋钮|开关|指示灯|操作面板|样本架|试剂架|废液瓶|缓冲液|清洗液|"
    r"测序芯片|Flow Cell|测序芯片|反应杯|样品杯)",
]
ATTR_PATTERNS = [
    r"(体积|尺寸|大小)[：:]\s*([0-9.]+\s*[×xX*]\s*[0-9.]+\s*[×xX*]\s*[0-9.]+\s*\w+)",
    r"(重量)[：:]\s*([0-9.]+\s*\w+)",
    r"(输入电压|工作电压|电源电压)[：:]\s*([0-9\-~.]+\s*\w+\s*,?\s*[0-9\-~]*\s*\w*)",
    r"(功率|额定功率|最大功率)[：:]\s*([0-9.]+\s*\w+)",
    r"(工作温度|使用温度)[：:]\s*([0-9\-~.]+°?C?\s*[至~到]\s*[0-9\-~.]+°?C?)",
    r"(湿度|相对湿度)[：:]\s*([0-9\-~.]+%?\s*[至~到]\s*[0-9\-~.]+%?\s*RH?)",
    r"(精度|准确度|分辨率)[：:]\s*([0-9.]+\s*\w+)",
    r"(测序速度|检测速度|通量)[：:]\s*([0-9.]+\s*\w+)",
    r"(型号|产品型号|规格型号)[：:]\s*(\S+[^，。\s])",
    r"(软件版本|固件版本|操作系统)[：:]\s*(\S+[^，。\s])",
]
FAULT_WORDS = ["故障", "失效", "异常", "错误", "无法", "不能", "不识别", "不工作", "不启动",
               "死机", "黑屏", "无信号", "无数据", "报警", "提示", "警告", "错误代码",
               "E-\\d+", "F-\\d+", "ERR-\\d+", "ERROR"]
REPAIR_WORDS = ["维修", "更换", "替换", "校准", "重置", "复位", "重新安装", "联系售后",
                "清洁", "消毒", "检查", "确认", "重启", "断电", "更换电源", "更换传感器"]


# ===== PDF 读取 =====
def read_pdf(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    text = "\n".join(doc[p].get_text() for p in range(doc.page_count))
    doc.close()
    return text


def read_pdf_from_bytes(data: bytes, filename: str = "upload.pdf") -> str:
    """从内存 bytes 读 PDF（Flask 上传场景）"""
    doc = fitz.open(stream=io.BytesIO(data), filetype="pdf")
    text = "\n".join(doc[p].get_text() for p in range(doc.page_count))
    doc.close()
    return text


# ===== 装备名识别 =====
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


# ===== 核心抽取 =====
def extract_from_text(text: str, equipment_name: str) -> list[dict]:
    """从单个装备 PDF 文本抽取三元组"""
    triples = []

    # 1. 装备整体属性
    for pat in ATTR_PATTERNS:
        for m in re.finditer(pat, text):
            triples.append({
                "head": equipment_name, "hl": "Equipment",
                "rel": "HAS_ATTRIBUTE",
                "tail": f"{m.group(1)}={m.group(2).strip()}", "tl": "Attribute",
            })

    # 2. 部件组成
    seen_comps = set()
    for pat in COMPONENT_PATTERNS:
        for m in re.finditer(pat, text):
            comp = m.group(1).strip()
            if comp not in seen_comps and len(comp) >= 2:
                seen_comps.add(comp)
                triples.append({
                    "head": equipment_name, "hl": "Equipment",
                    "rel": "HAS_COMPONENT",
                    "tail": comp, "tl": "Component",
                })

    # 3. 故障模式
    fault_sentences = []
    for sentence in re.split(r"[。！？\n]", text):
        sentence = sentence.strip()
        if 5 <= len(sentence) <= 200 and any(w in sentence for w in FAULT_WORDS):
            fault_sentences.append(sentence)
    for fs in fault_sentences[:15]:
        triples.append({
            "head": equipment_name, "hl": "Equipment",
            "rel": "HAS_FAULT_MODE",
            "tail": fs[:80], "tl": "Fault",
        })
        for rw in REPAIR_WORDS:
            if rw in fs:
                triples.append({
                    "head": fs[:80], "hl": "Fault",
                    "rel": "REPAIRED_BY",
                    "tail": rw, "tl": "Solution",
                })

    # 4. 功能
    func_pats = [
        r"(?:可用于|用于|支持|实现|能够)\s*([^，。；\n]{2,30})",
        r"(?:主要功能|功能)[：:]\s*([^，。；\n]{2,40})",
    ]
    for pat in func_pats:
        for m in re.finditer(pat, text):
            func = m.group(1).strip()
            if 4 <= len(func) <= 40:
                triples.append({
                    "head": equipment_name, "hl": "Equipment",
                    "rel": "PERFORMS_FUNCTION",
                    "tail": func, "tl": "Function",
                })

    # 去重
    seen = set(); uniq = []
    for t in triples:
        k = (t["head"], t["rel"], t["tail"])
        if k not in seen:
            seen.add(k); uniq.append(t)
    return uniq


def extract_from_pdf(pdf_path: str) -> dict:
    """一键从 PDF 文件抽取：返回 {equipment, triples, text_len, is_scanned}"""
    text = read_pdf(pdf_path)
    equipment = detect_equipment_name(text, pdf_path)
    triples = extract_from_text(text, equipment)
    return {
        "equipment": equipment,
        "triples": triples,
        "text_len": len(text),
        "is_scanned": len(text) < 50,  # 几乎无文字层 = 扫描件
    }


# ===== Neo4j 写入（MERGE 去重）=====
def merge_triples(driver, triples: list[dict]) -> dict:
    """
    把三元组 MERGE 进 Neo4j（不破坏已有节点，只补充新关系）
    返回 {added_nodes, added_rels, total}
    """
    added_nodes = 0
    added_rels = 0
    with driver.session() as s:
        for t in triples:
            hl, tl, rel = t["hl"], t["tl"], t["rel"]
            # 安全：跳过非法关系名
            if not re.match(r"^[A-Z_]+$", rel):
                continue
            try:
                # MERGE 节点
                r_a = s.run(f"MERGE (a:{hl} {{name: $h}}) RETURN count(a) AS c", h=t["head"]).single()
                if r_a["c"] == 0:
                    added_nodes += 1
                r_b = s.run(f"MERGE (b:{tl} {{name: $tl}}) RETURN count(b) AS c", tl=t["tail"]).single()
                if r_b["c"] == 0:
                    added_nodes += 1
                # MERGE 关系
                r_r = s.run(f"MATCH (a:{hl} {{name: $h}}), (b:{tl} {{name: $tl}}) MERGE (a)-[r:{rel}]->(b) RETURN count(r) AS c",
                           h=t["head"], tl=t["tail"]).single()
                if r_r["c"] == 0:
                    added_rels += 1
            except Exception as e:
                print(f"  ⚠ MERGE 失败: {t} → {e}")
    return {"added_nodes": added_nodes, "added_rels": added_rels, "total": len(triples)}
