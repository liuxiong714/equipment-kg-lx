"""
装备知识图谱 PoC v2 —— LLM 驱动，真实装备文档
模型: Ollama qwen3.5:4b
文档: 华大智造 DNBSEQ-E25RS/ARS 基因测序仪产品说明书 (60页 PDF)
存储: Neo4j (bolt://localhost:7687)

语义化节点标签: Equipment / Component / Fault / Solution / Function / Attribute
关系类型:      HAS_COMPONENT / HAS_ATTRIBUTE / FAULT_CAUSED_BY / ...
"""
import json, os, re, time, requests, sys
import fitz  # PyMuPDF
from neo4j import GraphDatabase

# ===== 配置 =====
OLLAMA_URL = "http://localhost:11434"
LLM_MODEL = "qwen3.5:4b"
LLM_TIMEOUT = 600          # 秒 — 小模型生成慢
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PWD = "eqkg2026"
PDF_PATH = r"E:\linux\fellow-student\16-zhoujiajia\2026-10-15-知识图谱\09-装备文档\11111\(无水印)04-便携式基因测序仪-产品说明书.pdf"

# 装备知识图谱 schema：允许的节点标签和关系类型
ALLOWED_LABELS = {"Equipment", "Component", "Fault", "Solution", "Function", "Attribute", "Process"}
ALLOWED_RELS = {
    "HAS_COMPONENT",       # 装备 → 部件
    "HAS_ATTRIBUTE",       # 装备/部件 → 属性
    "PERFORMS_FUNCTION",   # 装备/部件 → 功能
    "HAS_FAULT_MODE",      # 装备/部件 → 故障模式
    "FAULT_CAUSED_BY",     # 故障 → 原因
    "FAULT_HAS_SYMPTOM",   # 故障 → 症状
    "FAULT_LOCATED_IN",    # 故障 → 部位/组件
    "REPAIRED_BY",         # 故障 → 维修方案
    "HAS_MAINTENANCE_PROCESS",  # 装备 → 维护流程
    "IS_A",                # 子类关系
}

# ===== LLM Prompt 模板 =====
EXTRACTION_PROMPT = """你是一位装备知识图谱构建专家。请从以下装备手册文本中抽取结构化三元组，输出严格的 JSON 格式。

## 目标：
识别装备的 **部件组成、功能、属性、故障模式、故障原因、故障症状、维修方案、维护流程**，输出 (head, relation, tail) 三元组。

## 允许的节点标签（label）：
- Equipment (装备整体)
- Component (部件/子系统/零件)
- Fault (故障模式)
- Solution (维修方案/解决方法)
- Function (功能描述)
- Attribute (属性参数，如重量、尺寸、电压、型号等)
- Process (操作流程/维护流程)

## 允许的关系类型（relation）：
HAS_COMPONENT | HAS_ATTRIBUTE | PERFORMS_FUNCTION | HAS_FAULT_MODE |
FAULT_CAUSED_BY | FAULT_HAS_SYMPTOM | FAULT_LOCATED_IN | REPAIRED_BY |
HAS_MAINTENANCE_PROCESS | IS_A

## 输出格式（严格 JSON，不要任何解释）：
```json
[
  {{"head": "装备名称", "head_label": "Equipment", "relation": "HAS_COMPONENT", "tail": "部件名称", "tail_label": "Component"}},
  {{"head": "部件名称", "head_label": "Component", "relation": "HAS_ATTRIBUTE", "tail": "参数值(如电压:220V)", "tail_label": "Attribute"}}
]
```

## 装备手册文本：
---
{text_chunk}
---

现在请抽取三元组。记住：
1. 只抽文本中明确出现的信息，不要猜测
2. 关系类型必须从上面的列表中选
3. 输出严格 JSON 数组，无其他文字
4. 一条三元组对应一个事实"""

# ===== 辅助函数 =====
def llm_extract(text_chunk, chunk_idx=0):
    """调用 Ollama LLM 抽取三元组"""
    prompt = EXTRACTION_PROMPT.format(text_chunk=text_chunk[:6000])  # 限长避免 context 爆
    payload = {
        "model": LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"num_ctx": 8192, "temperature": 0.1}
    }
    t0 = time.time()
    try:
        resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=LLM_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        dt = time.time() - t0
        raw = data.get("response", "")
        # 解析 JSON
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if m:
            triples = json.loads(m.group())
            print(f"  LLM chunk#{chunk_idx}: {len(triples)} triples, {dt:.1f}s")
            return triples
        else:
            print(f"  LLM chunk#{chunk_idx}: no JSON array found in response ({dt:.1f}s)")
            print(f"    raw[:200]: {raw[:200]}")
            return []
    except Exception as e:
        dt = time.time() - t0
        print(f"  LLM chunk#{chunk_idx}: ERROR after {dt:.1f}s — {e}")
        return []

def read_pdf_chunks(pdf_path, chunk_size=15):
    """按 chunk_size 页分块读取 PDF"""
    doc = fitz.open(pdf_path)
    chunks = []
    total = doc.page_count
    for i in range(0, total, chunk_size):
        end = min(i + chunk_size, total)
        text = ""
        for p in range(i, end):
            text += doc[p].get_text() + "\n"
        chunks.append((f"p{i+1}-p{end}", text))
    doc.close()
    return chunks

def clean_triple(t):
    """清洗 LLM 输出的三元组"""
    head = str(t.get("head", "")).strip()
    tail = str(t.get("tail", "")).strip()
    rel = str(t.get("relation", "")).strip().upper()
    hl = str(t.get("head_label", "")).strip()
    tl = str(t.get("tail_label", "")).strip()
    if not head or not tail or not rel:
        return None
    if rel not in ALLOWED_RELS:
        return None
    if hl not in ALLOWED_LABELS:
        hl = "Component"
    if tl not in ALLOWED_LABELS:
        tl = "Component"
    return head, hl, rel, tail, tl

def write_to_neo4j(driver, triples):
    """写入 Neo4j（语义化标签）"""
    # 1. 清空旧数据
    with driver.session() as s:
        s.run("MATCH (n) DETACH DELETE n")
        print("  Neo4j 图谱已清空")

    # 2. 写入装备根节点
    with driver.session() as s:
        s.run("MERGE (e:Equipment {name: $name})", name="DNBSEQ-E25RS/ARS 基因测序仪")

    # 3. 按标签分组写入
    written = 0
    with driver.session() as s:
        for head, hl, rel, tail, tl in triples:
            s.run(f"""
                MERGE (a:{hl} {{name: $head}})
                MERGE (b:{tl} {{name: $tail}})
                MERGE (a)-[:{rel}]->(b)
            """, head=head, tail=tail)
            written += 1
    print(f"  写入三元组: {written}")

# ===== 主流程 =====
print("=" * 70)
print("装备知识图谱 PoC v2 —— LLM 驱动真实装备文档")
print(f"模型: {LLM_MODEL}  |  PDF: {os.path.basename(PDF_PATH)}")
print("=" * 70)

# Step 1: 读 PDF 分块
print("\n📖 Step 1: 读取 PDF 分块")
chunks = read_pdf_chunks(PDF_PATH, chunk_size=12)
print(f"  PDF 分块: {len(chunks)} 块，共 {sum(len(c[1]) for c in chunks)/1e4:.1f} 万字")

# Step 2: 逐块 LLM 抽取
print("\n🧠 Step 2: LLM 逐块抽取三元组")
all_triples = []
for idx, (chunk_id, text) in enumerate(chunks):
    print(f"\n  --- 块 {idx+1}/{len(chunks)} ({chunk_id}, {len(text)}字) ---")
    triples = llm_extract(text, chunk_idx=idx)
    cleaned = [c for t in triples if (c := clean_triple(t))]
    all_triples.extend(cleaned)

# 去重
seen = set()
unique = []
for t in all_triples:
    key = (t[0], t[2], t[3])
    if key not in seen:
        seen.add(key)
        unique.append(t)
all_triples = unique
print(f"\n  去重后三元组总数: {len(all_triples)}")

# Step 3: 写入 Neo4j
print("\n💾 Step 3: 写入 Neo4j")
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PWD))
write_to_neo4j(driver, all_triples)

# Step 4: 验证
print("\n🔍 Step 4: 图谱统计与查询")
with driver.session() as s:
    labels = s.run("MATCH (n) RETURN labels(n) AS l, count(n) AS c ORDER BY c DESC")
    print("  节点标签统计:")
    for row in labels:
        print(f"    {row['l'][0]:20s} × {row['c']}")

    rels = s.run("MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS c ORDER BY c DESC")
    print("  关系类型统计:")
    for row in rels:
        print(f"    {row['t']:28s} × {row['c']}")

    print("\n  —— 装备→部件 前 10 ——")
    rows = s.run("""
        MATCH (e:Equipment)-[:HAS_COMPONENT]->(c)
        RETURN e.name AS equip, c.name AS comp
        LIMIT 10
    """)
    for r in rows:
        print(f"    🚛 {r['equip']} ──▸ {r['comp']}")

    print("\n  —— 装备/部件→故障 前 10 ——")
    rows = s.run("""
        MATCH (e)-[:HAS_FAULT_MODE]->(f:Fault)
        RETURN e.name AS src, f.name AS fault
        LIMIT 10
    """)
    for r in rows:
        print(f"    ⚠ {r['src']} ──▸ {r['fault']}")

driver.close()

print("\n" + "=" * 70)
print("✅ PoC v2 完成！")
print("   Neo4j Browser:  http://localhost:7474  (neo4j / eqkg2026)")
print("   Cypher 查询:  MATCH (n)-[r]->(m) RETURN n,r,m LIMIT 50")
print("=" * 70)
