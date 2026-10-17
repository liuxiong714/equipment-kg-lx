"""
装备知识问答引擎 —— 规则模板 + LLM Text2Cypher 兜底
依赖: neo4j, requests (ollama)
"""
import json, os, re, time, requests
from neo4j import GraphDatabase

# ===== 连接配置 (from env) =====
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PWD = os.environ.get("NEO4J_PWD", "eqkg2026")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen2.5:7b")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PWD))

# ===== 图谱 Schema (用于 prompt 注入 + 安全校验) =====
GRAPH_SCHEMA = """
标签 (Labels): Equipment, Component, Fault, Function, Attribute
关系 (Relationships):
  - Equipment -[:HAS_COMPONENT]-> Component
  - Equipment -[:HAS_FAULT_MODE]-> Fault
  - Equipment -[:PERFORMS_FUNCTION]-> Function
  - Equipment -[:HAS_ATTRIBUTE]-> Attribute
"""
LABELS = ["Equipment", "Component", "Fault", "Function", "Attribute"]
RELS = ["HAS_COMPONENT", "HAS_FAULT_MODE", "PERFORMS_FUNCTION", "HAS_ATTRIBUTE"]

# ===== 规则模板 =====
# 装备中文名 → 图谱型号关键词映射 (用于 WHERE 过滤)
EQUIPMENT_ALIASES = {
    "测序仪": ["DNBSEQ", "测序"],
    "基因测序": ["DNBSEQ"],
    "POCT": ["POCT", "核酸"],
    "核酸检测": ["核酸"],
    "酶标": ["酶标"],
    "扫描电镜": ["电镜", "显微镜"],
    "荧光计": ["荧光", "Fluo"],
}

RULE_TEMPLATES = [
    # 装备有哪些部件
    {
        "patterns": [r"(?:哪些装备|什么装备)?(\S+)?(?:有哪些|有什么|包含|配备了|由哪些).*(部件|组件|零件)"],
        "label": "Equipment", "rel": "HAS_COMPONENT", "target": "Component",
    },
    # 装备有什么功能
    {
        "patterns": [r"(\S+)?(?:有哪些|有什么|能|可以|具备).*(功能)"],
        "label": "Equipment", "rel": "PERFORMS_FUNCTION", "target": "Function",
    },
    # 装备故障
    {
        "patterns": [r"(\S+)?(?:有哪些|有什么|常见的|主要的).*(?:故障|异常|失效|报错|错误)",
                     r"(\S+)?(?:故障|异常|失效|报错|错误|坏了).*(?:有哪些|有什么|会|常见)"],
        "label": "Equipment", "rel": "HAS_FAULT_MODE", "target": "Fault",
    },
    # 有哪些装备
    {
        "patterns": [r"(?:有哪些|有什么|列出|全部|所有).*(?:装备|仪器|设备|分析仪|测序仪)"],
        "label": "Equipment", "rel": None, "target": None,
    },
    # 装备属性
    {
        "patterns": [r"(\S+)?(?:参数|规格|属性|体积|重量|电压|功率)"],
        "label": "Equipment", "rel": "HAS_ATTRIBUTE", "target": "Attribute",
    },
]


def _resolve_where(question: str, label: str) -> str:
    """从问题里提取装备关键词，转换成 WHERE e.name CONTAINS ..."""
    for alias, keywords in EQUIPMENT_ALIASES.items():
        if alias in question:
            return f"WHERE e.name CONTAINS '{keywords[0]}'"
    return ""


def rule_match(question: str):
    """规则模板匹配 → Cypher 或 None"""
    for tpl in RULE_TEMPLATES:
        for pat in tpl["patterns"]:
            if re.search(pat, question):
                label = tpl["label"]
                if tpl["rel"] is None:
                    return f"MATCH (e:{label}) RETURN collect(e.name) AS equipments"
                where = _resolve_where(question, label)
                target = tpl["target"]
                return f"MATCH (e:{label})-[:{tpl['rel']}]->(c:{target}) {where} RETURN e.name AS equip, collect(c.name) AS items"
    return None


def run_cypher(cypher: str) -> list[dict]:
    """安全执行 Cypher —— 只读 + 强制 LIMIT"""
    # 安全: 禁止写操作
    forbidden = re.compile(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|CALL)\b", re.IGNORECASE)
    if forbidden.search(cypher):
        raise ValueError(f"禁止写操作: {cypher}")
    # 强制 LIMIT
    if not re.search(r"\bLIMIT\b", cypher, re.IGNORECASE):
        cypher = cypher.rstrip(";") + " LIMIT 200"
    with driver.session() as session:
        rows = list(session.run(cypher))
        return [dict(r) for r in rows]


def format_answer(question: str, rows: list[dict]) -> str:
    """把 Neo4j 返回格式化为可读中文"""
    if not rows:
        return "图谱里暂时没找到相关数据。可能该装备的 PDF 是扫描版未入库。"
    out = [f"**{question}** 的答案：\n"]
    for r in rows:
        for k, v in r.items():
            if isinstance(v, list):
                out.append(f"  **{k}**: {', '.join(str(x) for x in v)}")
            else:
                out.append(f"  **{k}**: {v}")
        out.append("")
    return "\n".join(out)


def llm_text2cypher(question: str, timeout: int = 120) -> str | None:
    """LLM 把自然语言转 Cypher。CPU 下很慢，作为兜底。"""
    prompt = f"""你是 Neo4j Cypher 专家。根据用户问题，输出一条只读取（只读）的 Cypher 查询。

可用图谱 Schema:
{GRAPH_SCHEMA}

规则:
1. 只能用上面列出的标签和关系
2. 只能 SELECT/MATCH，禁止 CREATE/DELETE/SET/MERGE/DROP
3. 必须加 LIMIT ≤ 100
4. 只输出 Cypher 查询，不要任何解释、markdown 或代码块

用户问题: {question}

Cypher:"""
    try:
        t0 = time.time()
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": LLM_MODEL, "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        elapsed = time.time() - t0
        if resp.status_code != 200:
            return None
        raw = resp.json().get("response", "").strip()
        # 从输出里提取 Cypher (去掉解释)
        cypher_match = re.search(r"(MATCH[\s\S]+?)(?:$|LIMIT\s*\d+)", raw, re.IGNORECASE)
        if cypher_match:
            cypher = cypher_match.group(0).strip()
            if not re.search(r"\bLIMIT\b", cypher, re.IGNORECASE):
                cypher += " LIMIT 50"
            print(f"  [LLM Text2Cypher] ({elapsed:.1f}s): {cypher}")
            return cypher
        return None
    except Exception as e:
        print(f"  [LLM 失败] {e}")
        return None


def ask(question: str, use_llm: bool = False) -> dict:
    """问答主入口"""
    print(f"\n❓ 问题: {question}")
    t0 = time.time()

    # 1. 先试规则模板 (瞬间返回)
    cypher = rule_match(question)
    if cypher:
        print(f"  [规则匹配] Cypher: {cypher}")
    elif use_llm:
        print("  [规则未命中 → LLM Text2Cypher]")
        cypher = llm_text2cypher(question, timeout=180)
    else:
        return {
            "mode": "none",
            "answer": "规则模板未命中。如需走 LLM 兜底，请传 use_llm=True 或在 Flask UI 勾选。",
            "elapsed": 0,
        }

    if not cypher:
        return {"mode": "none", "answer": "无法生成查询。", "elapsed": 0}

    # 2. 执行 Cypher
    try:
        rows = run_cypher(cypher)
    except Exception as e:
        return {"mode": "error", "answer": f"查询执行失败: {e}", "elapsed": time.time() - t0}

    answer = format_answer(question, rows)
    mode = "rule" if "规则匹配" in str(cypher) else "llm" if use_llm else "rule"
    elapsed = time.time() - t0
    print(f"  ✅ 完成 ({elapsed:.1f}s)")
    return {"mode": mode, "cypher": cypher, "rows": rows, "answer": answer, "elapsed": elapsed}


if __name__ == "__main__":
    # 命令行测试
    import sys
    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "测序仪有哪些部件"
    result = ask(q)
    print("\n" + "=" * 50)
    print(result.get("answer", result))
    if result.get("cypher"):
        print(f"\n[Cypher] {result['cypher']}")
