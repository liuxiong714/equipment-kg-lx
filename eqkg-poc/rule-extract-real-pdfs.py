"""
装备知识图谱 PoC v4 —— 规则抽取（CPU 可行，5 分钟跑完）
6 个真实装备 PDF → 语义化三元组 → Neo4j
"""
import json, os, re, time
import fitz
from neo4j import GraphDatabase

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PWD = os.environ.get("NEO4J_PWD", "eqkg2026")
PDF_DIR = os.environ.get("PDF_DIR", r"E:\linux\fellow-student\16-zhoujiajia\2026-10-15-知识图谱\09-装备文档\11111")

# ===== 规则定义 =====
# 常见装备名词
EQUIPMENT_KEYWORDS = ["测序仪", "分析仪", "检测仪", "显微镜", "酶标仪", "荧光计", "定量仪",
                      "PCR仪", "核酸检测", "基因测序", "POCT", "电泳仪", "离心机"]
# 部件名词（排除装备整体）
COMPONENT_PATTERNS = [
    r"(控制单元|测序单元|光学检测系统|电源模块|数据处理单元|主板|显示屏|触摸屏|键盘|打印机|传感器|"
    r"芯片槽|样本槽|试剂槽|管路|阀门|泵|电机|冷却系统|加热系统|温控模块|气体供应|液体供应|"
    r"光路系统|电子系统|机械系统|系统软件|固件|接口|USB|LAN|串口|电池|适配器|电源线|数据线|"
    r"外壳|面板|盖板|旋钮|开关|指示灯|显示屏|操作面板|样本架|试剂架|废液瓶|缓冲液|清洗液|"
    r"测序芯片|Flow Cell|测序芯片|反应杯|样品杯)",
]
# 属性模式（参数规格）
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
# 故障关键词
FAULT_WORDS = ["故障", "失效", "异常", "错误", "无法", "不能", "不识别", "不工作", "不启动",
               "死机", "黑屏", "无信号", "无数据", "报警", "提示", "警告", "错误代码",
               "E-\d+", "F-\d+", "ERR-\d+", "ERROR"]
# 维修/解决关键词
REPAIR_WORDS = ["维修", "更换", "替换", "校准", "重置", "复位", "重新安装", "联系售后",
                "清洁", "消毒", "检查", "确认", "重启", "断电", "更换电源", "更换传感器"]

def log(m): print(m, flush=True)

def read_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = "\n".join(doc[p].get_text() for p in range(doc.page_count))
    doc.close()
    return text

def extract_from_text(text, equipment_name):
    """从单个装备 PDF 文本抽取三元组"""
    triples = []

    # 1. 装备整体属性
    for pat in ATTR_PATTERNS:
        for m in re.finditer(pat, text):
            attr_name, attr_val = m.group(1), m.group(2)
            triples.append({
                "head": equipment_name, "hl": "Equipment",
                "rel": "HAS_ATTRIBUTE",
                "tail": f"{attr_name}={attr_val.strip()}", "tl": "Attribute"
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
                    "tail": comp, "tl": "Component"
                })

    # 3. 故障模式（用故障关键词匹配句子）
    fault_sentences = []
    for sentence in re.split(r"[。！？\n]", text):
        sentence = sentence.strip()
        if not sentence or len(sentence) < 5:
            continue
        if any(w in sentence for w in FAULT_WORDS):
            fault_sentences.append(sentence)

    for fs in fault_sentences[:15]:  # 限 15 个避免幻觉
        fault = fs[:80]  # 截断
        triples.append({
            "head": equipment_name, "hl": "Equipment",
            "rel": "HAS_FAULT_MODE",
            "tail": fault, "tl": "Fault"
        })
        # 同一故障句子里找维修关键词
        for rw in REPAIR_WORDS:
            if rw in fs:
                triples.append({
                    "head": fault, "hl": "Fault",
                    "rel": "REPAIRED_BY",
                    "tail": rw, "tl": "Solution"
                })

    # 4. 功能（找"可用于/用于/支持/实现"模式）
    func_pats = [
        r"(?:可用于|用于|支持|实现|能够)\s*([^，。；\n]{2,30})",
        r"(?:主要功能|功能)[：:]\s*([^，。；\n]{2,40})",
    ]
    for pat in func_pats:
        for m in re.finditer(pat, text):
            func = m.group(1).strip()
            if len(func) >= 4 and len(func) <= 40:
                triples.append({
                    "head": equipment_name, "hl": "Equipment",
                    "rel": "PERFORMS_FUNCTION",
                    "tail": func, "tl": "Function"
                })

    return triples

# ===== 主流程 =====
log("=" * 60)
log("装备 KG PoC v4 —— 规则抽取 + 真实 PDF")
log("=" * 60)

pdfs = sorted([f for f in os.listdir(PDF_DIR) if f.endswith(".pdf")])
log(f"\n发现 {len(pdfs)} 个 PDF:")
for p in pdfs: log(f"  - {p}")

all_triples = []
t0 = time.time()
for pdf_name in pdfs:
    pdf_path = os.path.join(PDF_DIR, pdf_name)
    # 先读 PDF，再从首页精确提取装备型号
    text = read_pdf(pdf_path)
    first_page_text = text[:3000]
    model_match = re.search(r"(?:型号|产品型号|规格型号)[：:]\s*([\w\-&]+)", first_page_text)
    if model_match:
        equipment_name = model_match.group(1)
    else:
        m = re.search(r"(DNBSEQ[-A-Z0-9&]+|MF[-A-Z0-9&]*|Fluo[-A-Z0-9&]*|iScanner[-A-Z0-9&]*)", first_page_text)
        if m:
            equipment_name = m.group(1)
        else:
            equipment_name = re.sub(r"^[\(\[无水印\)\]]*\d*[-－]\s*", "", pdf_name.replace(".pdf","").replace("_saved",""))

    log(f"\n--- {pdf_name} ---")
    log(f"  装备名: {equipment_name}")
    log(f"  PDF 文本长度: {len(text)} 字")

    triples = extract_from_text(text, equipment_name)
    log(f"  抽取三元组: {len(triples)}")
    # 按类型分组显示前 5
    by_type = {}
    for t in triples:
        by_type.setdefault(t["rel"], []).append(t)
    for rel, ts in sorted(by_type.items()):
        log(f"    {rel}: {len(ts)} 条")

    all_triples.extend(triples)

dt = time.time() - t0
# 去重
seen = set(); uniq = []
for t in all_triples:
    k = (t["head"], t["rel"], t["tail"])
    if k not in seen:
        seen.add(k); uniq.append(t)
all_triples = uniq
log(f"\n{'='*60}")
log(f"总耗时 {dt:.1f}s，去重后 {len(all_triples)} triples")

# 写 Neo4j
log(f"\n💾 写入 Neo4j...")
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PWD))
with driver.session() as s:
    s.run("MATCH (n) DETACH DELETE n")
    for t in all_triples:
        try:
            s.run(f"""
                MERGE (a:{t['hl']} {{name: $h}})
                MERGE (b:{t['tl']} {{name: $tl}})
                MERGE (a)-[:{t['rel']}]->(b)
            """, h=t["head"], tl=t["tail"])
        except Exception as e:
            log(f"  ⚠ 写入失败: {e}")

    n_nodes = s.run("MATCH (n) RETURN count(n)").single()[0]
    n_rels = s.run("MATCH ()-[rel]->() RETURN count(rel)").single()[0]

    log(f"\n✅ Neo4j: {n_nodes} 节点 / {n_rels} 关系")
    log(f"\n—— 节点标签分布 ——")
    for r in s.run("MATCH (n) RETURN labels(n)[0] AS l, count(n) AS c ORDER BY c DESC"):
        log(f"  {r['l']:15s} × {r['c']}")
    log(f"\n—— 关系类型分布 ——")
    for r in s.run("MATCH ()-[rel]->() RETURN type(rel) AS t, count(rel) AS c ORDER BY c DESC"):
        log(f"  {r['t']:28s} × {r['c']}")
    log(f"\n—— 装备→部件 示例 ——")
    for r in s.run("MATCH (e:Equipment)-[:HAS_COMPONENT]->(c) RETURN e.name AS e, c.name AS c LIMIT 20"):
        log(f"  🚛 {r['e']} ──▸ {r['c']}")
    log(f"\n—— 装备→故障 示例 ——")
    for r in s.run("MATCH (e:Equipment)-[:HAS_FAULT_MODE]->(f:Fault) RETURN e.name AS e, f.name AS f LIMIT 15"):
        log(f"  ⚠ {r['e']} ──▸ {r['f']}")
    log(f"\n—— 故障→维修 示例 ——")
    for r in s.run("MATCH (f:Fault)-[:REPAIRED_BY]->(s) RETURN f.name AS f, s.name AS s LIMIT 10"):
        log(f"  🔧 {r['f'][:30]} ──▸ {r['s']}")
    log(f"\n—— 装备→属性 示例 ——")
    for r in s.run("MATCH (e:Equipment)-[:HAS_ATTRIBUTE]->(a:Attribute) RETURN e.name AS e, a.name AS a LIMIT 15"):
        log(f"  📋 {r['e']} ──▸ {r['a']}")
    log(f"\n—— 装备→功能 示例 ——")
    for r in s.run("MATCH (e:Equipment)-[:PERFORMS_FUNCTION]->(f:Function) RETURN e.name AS e, f.name AS f LIMIT 10"):
        log(f"  🎯 {r['e']} ──▸ {r['f']}")

driver.close()

log(f"\n{'='*60}")
log(f"🎉 v4 规则抽取完成！")
log(f"   Neo4j Browser: http://localhost:7474 (neo4j / eqkg2026)")
log(f"   Cypher: MATCH (n)-[r]->(m) RETURN n,r,m LIMIT 50")
log(f"{'='*60}")
