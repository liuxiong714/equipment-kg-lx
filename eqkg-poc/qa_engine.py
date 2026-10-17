"""
装备知识问答引擎 v2 —— 本体对齐版
规则模板 + LLM Text2Cypher 兜底（注入本体 schema 上下文）
"""
import json, re, time, requests
from neo4j import GraphDatabase

from config import settings, neo4j_auth
from ontology import (
    ENTITY_TYPES, RELATION_TYPES,
    ALLOWED_LABELS, ALLOWED_RELATIONS,
    is_descendant,
)

# ===== 连接配置 =====
NEO4J_URI = settings.neo4j.uri
NEO4J_USER, NEO4J_PWD = neo4j_auth()
OLLAMA_URL = settings.ollama.url
LLM_MODEL = settings.ollama.model

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PWD))


# ============================================================
# 从 ontology.py 自动生成图谱 Schema 描述
# ============================================================
def _build_graph_schema() -> str:
    """动态构建 Neo4j 图谱 Schema 文本（用于 LLM prompt 注入）"""
    lines = ["## 节点标签 (按本体层级)\n"]
    # 只列前两层（太细的子类 LLM 记不住）
    for code, e in sorted(ENTITY_TYPES.items()):
        if e.level in ("根节点", "一级", "二级"):
            lines.append(f"  - {e.neo4j_label} ({e.code}) — {e.name_zh}")

    lines.append("\n## 关系类型 (domain → range 约束)\n")
    for code, r in sorted(RELATION_TYPES.items()):
        dom = ",".join(r.domain)
        rng = ",".join(r.range)
        lines.append(f"  - [{r.name_en}] ({r.name_zh}) — domain=[{dom}] → range=[{rng}]")

    lines.append("\n## 常用 Cypher 模式\n")
    lines.append("  装备有哪些部件: MATCH (e:E01)-[:matchedWith]->(c:E02) RETURN e.name, collect(c.name)")
    lines.append("  装备采用什么技术: MATCH (e:E01)-[:adopts]->(t:E03) RETURN e.name, collect(t.name)")
    lines.append("  装备执行什么任务: MATCH (e:E01)-[:performsTask]->(t:E07) RETURN e.name, collect(t.name)")
    lines.append("  装备有什么性能指标: MATCH (e:E01)-[:has]->(m:E13) RETURN e.name, collect(m.name)")
    lines.append("  装备依据什么标准: MATCH (e:E01)-[:basedOn]->(s:E14) RETURN e.name, collect(s.name)")
    lines.append("  适用于什么场所: MATCH (e:E01)-[:applicableTo]->(v:E09) RETURN e.name, collect(v.name)")
    lines.append("  针对什么病原体: MATCH (e:E01)-[:targets]->(p:E11) RETURN e.name, collect(p.name)")
    return "\n".join(lines)


GRAPH_SCHEMA = _build_graph_schema()


# ============================================================
# 规则模板（本体对齐版）
# ============================================================
# 装备别名 → 本体 code + 图查询关键词
EQUIPMENT_ALIASES = {
    "测序仪": ["E01_01", "DNBSEQ", "测序"],
    "基因测序": ["E01_01", "DNBSEQ", "测序"],
    "POCT": ["E01_01", "POCT"],
    "核酸检测": ["E01_01", "核酸"],
    "酶标": ["E01_04", "酶标"],
    "扫描电镜": ["E01_04", "电镜", "SEM"],
    "荧光计": ["E01_04", "荧光", "Fluo"],
    "检测仪": ["E01_01", "检测"],
}

# 通用本体查询（不依赖具体装备关键词）
RULE_TEMPLATES = [
    # ============ 装备有哪些部件 ============
    {
        "patterns": [
            r"(\S+)?(?:有哪些|有什么|包含|配备了|由哪些|主要)[^，。]*?(部件|组件|零件|模块|配件|附属)",
        ],
        "build": lambda q: _cypher_matched_with(q),
    },
    # ============ 装备采用什么技术/原理 ============
    {
        "patterns": [
            r"(\S+)?(?:采用|使用|基于|利用)[^，。]*?(技术|原理|测序方法|测序技术)",
        ],
        "build": lambda q: _cypher_adopts(q),
    },
    # ============ 装备执行什么任务 ============
    {
        "patterns": [
            r"(\S+)?(?:能|可以|具备|能够)[^，。]*?(做什么|干什么|完成|执行|进行)[^，。]*?(任务|工作|检测|测定)",
            r"(\S+)?(?:有哪些|有什么)[^，。]*?(任务|功能)",
        ],
        "build": lambda q: _cypher_performs_task(q),
    },
    # ============ 装备有什么性能指标/参数 ============
    {
        "patterns": [
            r"(\S+)?(?:参数|规格|性能|性能指标|体积|重量|电压|功率|精度|灵敏度|分辨率)",
        ],
        "build": lambda q: _cypher_has_metric(q),
    },
    # ============ 装备依据什么标准 ============
    {
        "patterns": [
            r"(\S+)?(?:依据|遵循|符合|满足)[^，。]*?(标准|规范|法规|GB|ISO|YY)",
        ],
        "build": lambda q: _cypher_based_on(q),
    },
    # ============ 装备适用于什么场所 ============
    {
        "patterns": [
            r"(\S+)?(?:适用于|可在|用于)[^，。]*?(场所|地点|场景|环境|实验室|现场)",
        ],
        "build": lambda q: _cypher_applicable_to(q),
    },
    # ============ 装备针对什么病原体 ============
    {
        "patterns": [
            r"(\S+)?(?:针对|检测|识别)[^，。]*?(病原体|病毒|细菌|真菌|病原微生物)",
        ],
        "build": lambda q: _cypher_targets(q),
    },
    # ============ 有哪些装备 ============
    {
        "patterns": [
            r"(?:有哪些|有什么|列出|全部|所有|存在)[^，。]*?(装备|仪器|设备|分析仪|测序仪|检测仪)",
        ],
        "build": lambda q: "MATCH (e:E01) RETURN collect(DISTINCT e.name) AS equipments",
    },
]


# ============================================================
# Cypher 构造函数（本体对齐版）
# ============================================================
def _resolve_equipment_where(question: str) -> str:
    """从问题提取装备关键词 → WHERE e.name CONTAINS ..."""
    for alias, keys in EQUIPMENT_ALIASES.items():
        if alias in question:
            return f"WHERE e.name CONTAINS '{keys[1]}'"
    return ""


def _resolve_equipment_label(question: str) -> str:
    """从问题提取装备子类 label → e:E01_01 / e:E01_04"""
    for alias, keys in EQUIPMENT_ALIASES.items():
        if alias in question:
            return keys[0]  # e.g. "E01_01"
    return "E01"  # 默认所有装备


def _cypher_matched_with(q: str) -> str:
    where = _resolve_equipment_where(q)
    label = _resolve_equipment_label(q)
    return f"MATCH (e:{label})-[:matchedWith]->(c) {where} RETURN e.name AS equip, collect(c.name) AS items"


def _cypher_adopts(q: str) -> str:
    where = _resolve_equipment_where(q)
    label = _resolve_equipment_label(q)
    return f"MATCH (e:{label})-[:adopts]->(t) {where} RETURN e.name AS equip, collect(t.name) AS items"


def _cypher_performs_task(q: str) -> str:
    where = _resolve_equipment_where(q)
    label = _resolve_equipment_label(q)
    return f"MATCH (e:{label})-[:performsTask]->(t) {where} RETURN e.name AS equip, collect(t.name) AS items"


def _cypher_has_metric(q: str) -> str:
    where = _resolve_equipment_where(q)
    label = _resolve_equipment_label(q)
    return f"MATCH (e:{label})-[:has]->(m) {where} RETURN e.name AS equip, collect(m.name) AS items"


def _cypher_based_on(q: str) -> str:
    where = _resolve_equipment_where(q)
    label = _resolve_equipment_label(q)
    return f"MATCH (e:{label})-[:basedOn]->(s) {where} RETURN e.name AS equip, collect(s.name) AS items"


def _cypher_applicable_to(q: str) -> str:
    where = _resolve_equipment_where(q)
    label = _resolve_equipment_label(q)
    return f"MATCH (e:{label})-[:applicableTo]->(v) {where} RETURN e.name AS equip, collect(v.name) AS items"


def _cypher_targets(q: str) -> str:
    where = _resolve_equipment_where(q)
    label = _resolve_equipment_label(q)
    return f"MATCH (e:{label})-[:targets]->(p) {where} RETURN e.name AS equip, collect(p.name) AS items"


# ============================================================
# 规则引擎核心
# ============================================================
def rule_match(question: str) -> str | None:
    """规则模板匹配 → Cypher 或 None"""
    for tpl in RULE_TEMPLATES:
        for pat in tpl["patterns"]:
            if re.search(pat, question):
                return tpl["build"](question)
    return None


# ============================================================
# Cypher 执行（安全只读）
# ============================================================
def run_cypher(cypher: str) -> list[dict]:
    """安全执行 Cypher —— 只读 + 强制 LIMIT"""
    forbidden = re.compile(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|CALL)\b", re.IGNORECASE)
    if forbidden.search(cypher):
        raise ValueError(f"禁止写操作: {cypher}")
    if not re.search(r"\bLIMIT\b", cypher, re.IGNORECASE):
        cypher = cypher.rstrip(";") + " LIMIT 200"
    with driver.session() as session:
        rows = list(session.run(cypher))
        return [dict(r) for r in rows]


# ============================================================
# 答案格式化
# ============================================================
def format_answer(question: str, rows: list[dict]) -> str:
    """把 Neo4j 返回格式化为可读中文"""
    if not rows:
        return "图谱里暂时没找到相关数据。可能该装备的 PDF 是扫描版未入库，或还没有这类关系。"
    out = [f"**{question}** 的答案：\n"]
    for r in rows:
        for k, v in r.items():
            if isinstance(v, list):
                if v and isinstance(v[0], str) and len(v[0]) > 40:
                    # 列表项太长（属性值），换行展示
                    items = "\n".join(f"    · {x}" for x in v)
                    out.append(f"  **{k}**: {items}")
                else:
                    out.append(f"  **{k}**: {', '.join(str(x) for x in v)}")
            else:
                out.append(f"  **{k}**: {v}")
        out.append("")
    return "\n".join(out)


# ============================================================
# LLM Text2Cypher（注入本体 schema 上下文）
# ============================================================
def llm_text2cypher(question: str, timeout: int = 120) -> str | None:
    """LLM 把自然语言转 Cypher。CPU 下很慢，作为兜底。"""
    prompt = f"""你是 Neo4j Cypher 专家。根据用户问题，输出一条只读取的 Cypher 查询。

图谱 Schema:
{GRAPH_SCHEMA}

规则:
1. 只能用上面列出的标签和关系名（英文原名，不翻译）
2. 只能 MATCH/RETURN/OPTIONAL MATCH，禁止 CREATE/DELETE/SET/MERGE/DROP
3. 可以用 WHERE e.name CONTAINS '关键词' 过滤装备
4. 必须加 LIMIT ≤ 100
5. 只输出 Cypher 查询，不要任何解释、markdown、代码块或前后缀

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
            print(f"  [LLM HTTP {resp.status_code}]")
            return None
        raw = resp.json().get("response", "").strip()
        cypher_match = re.search(r"(MATCH[\s\S]+?)(?:LIMIT\s*\d+|$)", raw, re.IGNORECASE)
        if cypher_match:
            cypher = cypher_match.group(0).strip()
            if not re.search(r"\bLIMIT\b", cypher, re.IGNORECASE):
                cypher += " LIMIT 50"
            print(f"  [LLM Text2Cypher] ({elapsed:.1f}s): {cypher}")
            return cypher
        print(f"  [LLM 输出无法解析] raw[:200]={raw[:200]}")
        return None
    except Exception as e:
        print(f"  [LLM 失败] {e}")
        return None


# ============================================================
# 问答主入口
# ============================================================
def ask(question: str, use_llm: bool = False) -> dict:
    print(f"\n❓ 问题: {question}")
    t0 = time.time()

    cypher = rule_match(question)
    if cypher:
        print(f"  [规则匹配] {cypher}")
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

    try:
        rows = run_cypher(cypher)
    except Exception as e:
        return {"mode": "error", "answer": f"查询执行失败: {e}", "elapsed": time.time() - t0}

    answer = format_answer(question, rows)
    mode = "rule" if rule_match(question) else "llm" if use_llm else "rule"
    elapsed = time.time() - t0
    print(f"  ✅ 完成 ({elapsed:.1f}s), {len(rows)} 行")
    return {"mode": mode, "cypher": cypher, "rows": rows, "answer": answer, "elapsed": elapsed}


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "测序仪有哪些部件"
    result = ask(q)
    print("\n" + "=" * 50)
    print(result.get("answer", result))
    if result.get("cypher"):
        print(f"\n[Cypher] {result['cypher']}")
