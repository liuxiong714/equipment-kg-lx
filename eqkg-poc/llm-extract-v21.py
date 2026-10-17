"""
装备知识图谱 PoC v2.1 —— 小块 + 短 prompt + flush
先跑前 2 块验证，再决定是否全量
"""
import json, os, re, time, requests, sys
import fitz
from neo4j import GraphDatabase

# ===== 配置 =====
OLLAMA_URL = "http://localhost:11434"
LLM_MODEL = "qwen3.5:4b"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PWD = "eqkg2026"
PDF_PATH = r"E:\linux\fellow-student\16-zhoujiajia\2026-10-15-知识图谱\09-装备文档\11111\(无水印)04-便携式基因测序仪-产品说明书.pdf"

ALLOWED_LABELS = {"Equipment", "Component", "Fault", "Solution", "Function", "Attribute", "Process"}
ALLOWED_RELS = {
    "HAS_COMPONENT", "HAS_ATTRIBUTE", "PERFORMS_FUNCTION", "HAS_FAULT_MODE",
    "FAULT_CAUSED_BY", "FAULT_HAS_SYMPTOM", "FAULT_LOCATED_IN", "REPAIRED_BY",
    "HAS_MAINTENANCE_PROCESS", "IS_A",
}

PROMPT = ("从装备手册抽取(head,relation,tail)三元组，输出严格JSON数组。"
"关系仅可选：HAS_COMPONENT/HAS_ATTRIBUTE/PERFORMS_FUNCTION/HAS_FAULT_MODE/FAULT_CAUSED_BY/"
"FAULT_HAS_SYMPTOM/FAULT_LOCATED_IN/REPAIRED_BY/HAS_MAINTENANCE_PROCESS/IS_A。"
"节点label仅可选：Equipment/Component/Fault/Solution/Function/Attribute/Process。"
"文本如下：\\n{text}\\n\\n返回JSON，不要其他文字。")

def log(msg):
    print(msg, flush=True)

def llm_extract(text, idx):
    # 限 4000 字符进 prompt（CPU 推理慢，控长）
    text = text[:4000]
    prompt = PROMPT.format(text=text.replace("{", "[").replace("}", "]"))  # 防 format 干扰
    payload = {"model": LLM_MODEL, "prompt": prompt, "stream": False,
               "options": {"num_ctx": 8192, "temperature": 0.05}}
    t0 = time.time()
    log(f"  [LLM chunk#{idx}] 请求已发出，等待响应...")
    try:
        resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=900)
        resp.raise_for_status()
        data = resp.json()
        dt = time.time() - t0
        raw = data.get("response", "")
        # 尝试多种 JSON 提取
        m = re.search(r"\[[\s\S]*\]", raw)
        if not m:
            m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            try:
                triples = json.loads(m.group())
                if isinstance(triples, dict):
                    triples = triples.get("triples", triples.get("result", []))
                log(f"  [LLM chunk#{idx}] ✅ {len(triples)} triples in {dt:.0f}s (eval={data.get('eval_count','?')} tok)")
                return triples
            except Exception as e:
                log(f"  [LLM chunk#{idx}] ⚠ JSON parse fail: {e}; raw[:300]={raw[:300]}")
                return []
        else:
            log(f"  [LLM chunk#{idx}] ⚠ no JSON; raw[:300]={raw[:300]}")
            return []
    except requests.exceptions.Timeout:
        log(f"  [LLM chunk#{idx}] ❌ TIMEOUT after {time.time()-t0:.0f}s")
        return []
    except Exception as e:
        log(f"  [LLM chunk#{idx}] ❌ ERROR after {time.time()-t0:.0f}s — {e}")
        return []

def clean(t):
    h = str(t.get("head", "")).strip()
    r = str(t.get("relation", t.get("rel", ""))).strip().upper().replace("-", "_")
    tl = str(t.get("tail_label", t.get("head_type", ""))).strip()
    tail = str(t.get("tail", t.get("object", ""))).strip()
    trl = str(t.get("tail_label", t.get("tail_type", ""))).strip()
    if not h or not tail or not r or r not in ALLOWED_RELS:
        return None
    hl = tl if tl in ALLOWED_LABELS else "Component"
    tl_ = trl if trl in ALLOWED_LABELS else "Component"
    return {"head": h, "hl": hl, "rel": r, "tail": tail, "tl": tl_}

# ===== 主流程 =====
log("=" * 60)
log("装备 KG PoC v2.1 —— LLM (qwen3.5:4b) + 华大智造测序仪 PDF")
log("=" * 60)

doc = fitz.open(PDF_PATH)
total = doc.page_count
log(f"\n📖 PDF 共 {total} 页，开始分块 (6 页/块)")

# 只处理前 3 块验证，再决定全量
MAX_CHUNKS = 3
all_triples = []
ci = 0
for start in range(0, total, 6):
    ci += 1
    if ci > MAX_CHUNKS:
        break
    end = min(start + 6, total)
    text = "".join(doc[p].get_text() for p in range(start, end))
    log(f"\n--- 块 #{ci}: p{start+1}-p{end} ({len(text)}字) ---")
    raw = llm_extract(text, ci)
    cleaned = [c for t in raw if (c := clean(t))]
    all_triples.extend(cleaned)
doc.close()

# 去重
seen = set(); unique = []
for t in all_triples:
    k = (t["head"], t["rel"], t["tail"])
    if k not in seen:
        seen.add(k); unique.append(t)
all_triples = unique
log(f"\n去重后: {len(all_triples)} triples")
for t in all_triples[:20]:
    log(f"  ({t['hl']}) {t['head']} -[{t['rel']}]-> ({t['tl']}) {t['tail']}")

# 写 Neo4j
log(f"\n💾 写入 Neo4j...")
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PWD))
with driver.session() as s:
    s.run("MATCH (n) DETACH DELETE n")
    s.run("MERGE (e:Equipment {name: 'DNBSEQ-E25RS/ARS 基因测序仪'})")
    for t in all_triples:
        s.run(f"""
            MERGE (a:{t['hl']} {{name: $h}})
            MERGE (b:{t['tl']} {{name: $tl}})
            MERGE (a)-[:{t['rel']}]->(b)
        """, h=t["head"], tl=t["tail"])
    n = s.run("MATCH (n) RETURN count(n)").single()[0]
    r = s.run("MATCH ()-[rel]->() RETURN count(rel)").single()[0]
log(f"✅ Neo4j: {n} nodes / {r} rels")
driver.close()
