"""
装备知识图谱 PoC v3 —— qwen2.5:7b + TSV + 真实 PDF + 语义化 Neo4j
qwen2.5:7b 无 thinking，56s/块，10 块 ≈ 10 分钟
"""
import json, os, re, time, requests
import fitz
from neo4j import GraphDatabase

OLLAMA_URL = "http://localhost:11434"
MODEL = "qwen2.5:7b"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_PWD = "eqkg2026"
PDF_PATH = r"E:\linux\fellow-student\16-zhoujiajia\2026-10-15-知识图谱\09-装备文档\11111\(无水印)04-便携式基因测序仪-产品说明书.pdf"

ALLOWED_RELS = {"HAS_COMPONENT","HAS_ATTRIBUTE","PERFORMS_FUNCTION","HAS_FAULT_MODE",
                "FAULT_CAUSED_BY","FAULT_HAS_SYMPTOM","FAULT_LOCATED_IN","REPAIRED_BY",
                "HAS_MAINTENANCE_PROCESS","IS_A"}
LABEL_HINTS = {"E":"Equipment","C":"Component","F":"Fault","S":"Solution","A":"Attribute","P":"Process"}

PROMPT = ("从装备手册抽三元组，每行 tab 分隔，格式: "
          "装备名\\关系\\部件或属性值\\尾标签(E装备/C部件/F故障/S方案/A属性/P流程)\n"
          "关系仅用以下英文: HAS_COMPONENT HAS_ATTRIBUTE PERFORMS_FUNCTION HAS_FAULT_MODE FAULT_CAUSED_BY FAULT_HAS_SYMPTOM FAULT_LOCATED_IN REPAIRED_BY HAS_MAINTENANCE_PROCESS IS_A\n"
          "最多输出15行，只抽文本中明确出现的事实。\n手册文本:\n{text}")

def log(m): print(m, flush=True)

def llm_call(text, idx):
    text = text[:3000]
    prompt = PROMPT.replace("{text}", text)
    payload = {"model": MODEL, "prompt": prompt, "stream": False,
               "options": {"num_ctx": 8192, "temperature": 0.0}}
    t0 = time.time()
    try:
        r = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=400)
        d = r.json()
        dt = time.time() - t0
        resp = d.get("response", "")
        log(f"  chunk#{idx} ✅ {dt:.0f}s eval={d.get('eval_count','?')}tok")
        return resp
    except requests.exceptions.Timeout:
        log(f"  chunk#{idx} ❌ 400s TIMEOUT")
        return None
    except Exception as e:
        log(f"  chunk#{idx} ❌ {e}")
        return None

def parse_tsv(raw):
    triples = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"): continue
        line = re.sub(r"^\d+[\.\)、]\s*", "", line)
        # 支持 tab / 中文斜杠 / 竖线 分隔
        parts = re.split(r"\s*\t\s*|\s*/\s*|\s*\|\s*", line)
        if len(parts) < 3: continue
        head, rel, tail = parts[0].strip(), parts[1].strip().upper(), parts[2].strip()
        # 关系归一化（防 LLM 输出中文）
        rel_map = {
            "组成":"HAS_COMPONENT", "包含":"HAS_COMPONENT", "部件":"HAS_COMPONENT",
            "功能":"PERFORMS_FUNCTION", "执行":"PERFORMS_FUNCTION",
            "故障":"HAS_FAULT_MODE", "异常":"HAS_FAULT_MODE",
            "原因":"FAULT_CAUSED_BY", "导致":"FAULT_CAUSED_BY",
            "症状":"FAULT_HAS_SYMPTOM", "表现":"FAULT_HAS_SYMPTOM",
            "维修":"REPAIRED_BY", "解决":"REPAIRED_BY", "更换":"REPAIRED_BY",
            "属性":"HAS_ATTRIBUTE", "参数":"HAS_ATTRIBUTE",
            "流程":"HAS_MAINTENANCE_PROCESS", "步骤":"HAS_MAINTENANCE_PROCESS",
        }
        rel = rel_map.get(rel, rel.replace("-", "_").replace(" ", "_"))
        if rel not in ALLOWED_RELS: continue
        # 尾节点标签推断
        tail_label = "Component"
        tl_hint = parts[3].strip().upper() if len(parts) > 3 else ""
        if tl_hint in LABEL_HINTS: tail_label = LABEL_HINTS[tl_hint]
        elif rel == "HAS_ATTRIBUTE": tail_label = "Attribute"
        elif "故障" in tail or "失效" in tail or "异常" in tail: tail_label = "Fault"
        elif "更换" in tail or "步骤" in tail or "方案" in tail: tail_label = "Solution"
        triples.append({"head": head, "rel": rel, "tail": tail, "tl": tail_label})
    return triples

# ===== 主流程 =====
log("=" * 60)
log(f"装备 KG PoC v3 —— {MODEL} (no thinking) + 华大智造测序仪 PDF")
log("=" * 60)

doc = fitz.open(PDF_PATH)
total = doc.page_count
chunks = []
for s in range(0, total, 6):
    e = min(s + 6, total)
    txt = "".join(doc[p].get_text() for p in range(s, e))
    chunks.append((f"p{s+1}-p{e}", txt))
doc.close()
log(f"PDF {total}页 → {len(chunks)}块 (6页/块)")

all_triples = []
t0_all = time.time()
for idx, (cid, txt) in enumerate(chunks):
    log(f"\n--- 块 #{idx+1}/{len(chunks)}: {cid} ({len(txt)}字) ---")
    raw = llm_call(txt, idx+1)
    if raw:
        triples = parse_tsv(raw)
        if triples:
            log(f"  解析 {len(triples)} triples:")
            for t in triples[:5]:
                log(f"    ({t['head']}) -[{t['rel']}]-> ({t['tl']}) {t['tail']}")
            all_triples.extend(triples)
        else:
            log(f"  raw[:300]: {raw[:300]}")

dt_total = time.time() - t0_all
# 去重
seen = set(); uniq = []
for t in all_triples:
    k = (t["head"], t["rel"], t["tail"])
    if k not in seen:
        seen.add(k); uniq.append(t)
all_triples = uniq
log(f"\n{'='*60}")
log(f"总耗时 {dt_total:.0f}s，去重后 {len(all_triples)} triples")

# 写 Neo4j
log(f"\n💾 写入 Neo4j...")
driver = GraphDatabase.driver(NEO4J_URI, auth=("neo4j", NEO4J_PWD))
with driver.session() as s:
    s.run("MATCH (n) DETACH DELETE n")
    for t in all_triples:
        head_label = "Equipment" if any(k in t["head"] for k in ["测序仪","仪器","系统","分析仪","检测仪","显微镜","酶标仪","荧光"]) else "Component"
        if t["rel"] == "HAS_ATTRIBUTE": head_label = "Component"
        if t["rel"] == "HAS_FAULT_MODE": head_label = "Component"
        s.run(f"""
            MERGE (a:{head_label} {{name: $h}})
            MERGE (b:{t['tl']} {{name: $tl}})
            MERGE (a)-[:{t['rel']}]->(b)
        """, h=t["head"], tl=t["tail"])

    n_nodes = s.run("MATCH (n) RETURN count(n)").single()[0]
    n_rels = s.run("MATCH ()-[rel]->() RETURN count(rel)").single()[0]

    log(f"\n✅ Neo4j: {n_nodes} 节点 / {n_rels} 关系")
    log(f"\n节点标签分布:")
    for r in s.run("MATCH (n) RETURN labels(n)[0] AS l, count(n) AS c ORDER BY c DESC"):
        log(f"  {r['l']:20s} × {r['c']}")
    log(f"\n关系类型分布:")
    for r in s.run("MATCH ()-[rel]->() RETURN type(rel) AS t, count(rel) AS c ORDER BY c DESC"):
        log(f"  {r['t']:28s} × {r['c']}")

    log(f"\n—— 装备→部件 ——")
    for r in s.run("MATCH (e:Equipment)-[:HAS_COMPONENT]->(c) RETURN e.name AS e, c.name AS c LIMIT 15"):
        log(f"  🚛 {r['e']} ──▸ {r['c']}")
    log(f"\n—— 装备→故障 ——")
    for r in s.run("MATCH (e)-[:HAS_FAULT_MODE]->(f:Fault) RETURN e.name AS e, f.name AS f LIMIT 15"):
        log(f"  ⚠ {r['e']} ──▸ {r['f']}")
    log(f"\n—— 故障→维修 ——")
    for r in s.run("MATCH (f:Fault)-[:REPAIRED_BY]->(s) RETURN f.name AS f, s.name AS s LIMIT 15"):
        log(f"  🔧 {r['f']} ──▸ {r['s']}")

driver.close()
log(f"\n🎉 完成！")
log(f"   Neo4j Browser: http://localhost:7474  (neo4j / eqkg2026)")
log(f"   Cypher 查看全图: MATCH (n)-[r]->(m) RETURN n,r,m LIMIT 50")
