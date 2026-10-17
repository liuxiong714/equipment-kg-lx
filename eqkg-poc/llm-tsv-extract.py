"""
LLM 抽装备三元组 —— CPU 极端优化版
qwen3.5:4b + 纯 CPU + TSV 极简输出 + 每块限 10 条 + 2 分钟超时
"""
import json, os, re, time, requests
import fitz
from neo4j import GraphDatabase

OLLAMA_URL = "http://localhost:11434"
MODEL = "qwen3.5:4b"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_PWD = "eqkg2026"
PDF_PATH = r"E:\linux\fellow-student\16-zhoujiajia\2026-10-15-知识图谱\09-装备文档\11111\(无水印)04-便携式基因测序仪-产品说明书.pdf"

ALLOWED_RELS = {"HAS_COMPONENT","HAS_ATTRIBUTE","PERFORMS_FUNCTION","HAS_FAULT_MODE",
                "FAULT_CAUSED_BY","FAULT_HAS_SYMPTOM","FAULT_LOCATED_IN","REPAIRED_BY",
                "HAS_MAINTENANCE_PROCESS","IS_A"}
LABEL_HINTS = {"E":"Equipment","C":"Component","F":"Fault","S":"Solution","A":"Attribute","P":"Process"}

PROMPT = """从装备手册抽三元组，每行 TSV 格式：
装备名\关系\部件或属性值\尾节点标签(E装备/C部件/F故障/S方案/A属性/P流程)
关系仅用: HAS_COMPONENT HAS_ATTRIBUTE PERFORMS_FUNCTION HAS_FAULT_MODE FAULT_CAUSED_BY FAULT_HAS_SYMPTOM FAULT_LOCATED_IN REPAIRED_BY HAS_MAINTENANCE_PROCESS IS_A
最多输出10行，只抽明确出现的事实。手册：
{text}"""

def log(m): print(m, flush=True)

def call_llm(text, idx, max_s=150):
    # 限 2500 字
    text = text[:2500]
    prompt = PROMPT.replace("{text}", text)
    payload = {"model": MODEL, "prompt": prompt, "stream": False,
               "options": {"num_ctx": 4096, "temperature": 0.0}}
    t0 = time.time()
    log(f"  chunk#{idx} 请求发出 ({len(text)}字)...")
    try:
        r = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=max_s)
        r.raise_for_status()
        data = r.json()
        dt = time.time() - t0
        raw = data.get("response", "")
        log(f"  chunk#{idx} ✅ {dt:.0f}s, raw[:200]=|{raw[:200]}|")
        return raw
    except requests.exceptions.Timeout:
        log(f"  chunk#{idx} ❌ TIMEOUT {max_s}s")
        return None
    except Exception as e:
        log(f"  chunk#{idx} ❌ {e}")
        return None

def parse_tsv(raw):
    """把 TSV 输出解析成三元组"""
    triples = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # 去除行首的数字序号
        line = re.sub(r"^\d+[\.\)、]\s*", "", line)
        # 尝试按 \t 或 / 或 | 分割
        parts = re.split(r"\s*\t\s*|\s*/\s*|\s*\|\s*|\s*,\s*|\s*—\s*|\s*-\s*", line)
        if len(parts) < 3:
            continue
        head, rel, tail = parts[0].strip(), parts[1].strip().upper(), parts[2].strip()
        # 关系归一化
        rel_norm = rel.replace("-", "_").replace(" ", "_")
        if rel_norm == "组成": rel_norm = "HAS_COMPONENT"
        elif rel_norm in ("功能", "执行"): rel_norm = "PERFORMS_FUNCTION"
        elif rel_norm in ("故障", "异常"): rel_norm = "HAS_FAULT_MODE"
        elif rel_norm in ("原因", "导致"): rel_norm = "FAULT_CAUSED_BY"
        elif rel_norm in ("维修", "解决"): rel_norm = "REPAIRED_BY"
        elif rel_norm in ("属性", "参数"): rel_norm = "HAS_ATTRIBUTE"
        if rel_norm not in ALLOWED_RELS:
            continue
        # 尾节点标签推断
        tail_label = "Component"
        tl_hint = parts[3].strip().upper() if len(parts) > 3 else ""
        if tl_hint in LABEL_HINTS:
            tail_label = LABEL_HINTS[tl_hint]
        elif rel_norm == "HAS_ATTRIBUTE": tail_label = "Attribute"
        elif "故障" in tail or "失效" in tail or "异常" in tail or "不" in tail: tail_label = "Fault"
        elif "更换" in tail or "步骤" in tail: tail_label = "Solution"
        triples.append({"head": head, "rel": rel_norm, "tail": tail, "tl": tail_label})
    return triples

# ===== 主流程 =====
log("=" * 60)
log("LLM TSV 抽装备三元组 (qwen3.5:4b CPU, 150s/块 timeout)")
log("=" * 60)

doc = fitz.open(PDF_PATH)
total_pages = doc.page_count
chunks = []
pages_per_chunk = 6
for s in range(0, total_pages, pages_per_chunk):
    e = min(s + pages_per_chunk, total_pages)
    txt = "".join(doc[p].get_text() for p in range(s, e))
    chunks.append((f"p{s+1}-p{e}", txt))
doc.close()

log(f"PDF 共 {total_pages} 页 → {len(chunks)} 块")

all_triples = []
for idx, (cid, txt) in enumerate(chunks[:3]):  # 先跑前 3 块
    log(f"\n--- 块 #{idx+1}: {cid} ({len(txt)}字) ---")
    raw = call_llm(txt, idx+1, max_s=150)
    if raw:
        triples = parse_tsv(raw)
        log(f"  解析得到 {len(triples)} triples")
        for t in triples:
            log(f"    {t['head']} -[{t['rel']}]-> ({t['tl']}) {t['tail']}")
        all_triples.extend(triples)

# 去重
seen = set(); uniq = []
for t in all_triples:
    k = (t["head"], t["rel"], t["tail"])
    if k not in seen:
        seen.add(k); uniq.append(t)
all_triples = uniq
log(f"\n去重后: {len(all_triples)} triples")

# 写 Neo4j
log(f"\n💾 写入 Neo4j...")
driver = GraphDatabase.driver(NEO4J_URI, auth=("neo4j", NEO4J_PWD))
with driver.session() as s:
    s.run("MATCH (n) DETACH DELETE n")
    for t in all_triples:
        # head 默认 Component，Equipment 特殊处理
        head_label = "Equipment" if "测序仪" in t["head"] or "仪器" in t["head"] or "系统" in t["head"] else "Component"
        if t["rel"] == "HAS_ATTRIBUTE": head_label = "Component"
        s.run(f"""
            MERGE (a:{head_label} {{name: $h}})
            MERGE (b:{t['tl']} {{name: $tl}})
            MERGE (a)-[:{t['rel']}]->(b)
        """, h=t["head"], tl=t["tail"])
    n = s.run("MATCH (n) RETURN count(n)").single()[0]
    r = s.run("MATCH ()-[rel]->() RETURN count(rel)").single()[0]
log(f"✅ Neo4j: {n} nodes / {r} rels")

# 快速图谱预览
with driver.session() as s:
    log(f"\n图谱示例 (前 10 条):")
    for row in s.run("MATCH (a)-[r]->(b) RETURN a.name AS a, type(r) AS r, b.name AS b LIMIT 10"):
        log(f"  {row['a']} -[{row['r']}]-> {row['b']}")
driver.close()

log(f"\n🎉 完成！Neo4j Browser: http://localhost:7474 (neo4j / eqkg2026)")
