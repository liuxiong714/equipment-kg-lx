"""
装备知识图谱 PoC —— 规则 + 正则从测试手册抽取三元组写入 Neo4j
无 LLM 依赖，2 分钟内跑通 PDF/文本 → Neo4j 管道
"""
import re
import os
from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PWD = "eqkg2026"
TEST_MANUAL = r"E:\linux\trae_project\sfzb\eqkg-poc\test-equipment-manual.txt"

# ===== 1. 解析测试手册 =====
print("=" * 60)
print("📖 第 1 步：解析装备测试手册")
print("=" * 60)

with open(TEST_MANUAL, encoding="utf-8") as f:
    text = f.read()

# 提取装备型号
equip_match = re.search(r"装备型号[:：]\s*([A-Za-z0-9\-]+)", text)
equip_model = equip_match.group(1) if equip_match else "Unknown"
print(f"  发现装备型号: {equip_model}")

# 提取装备属性
attrs = re.findall(r"([\u4e00-\u9fa5A-Za-z]+)[：:]\s*([0-9]+\s*[\u4e00-\u9fa5A-Za-z/·]+)", text)
print(f"  发现装备属性对: {len(attrs)}")
for k, v in attrs[:5]:
    print(f"    {k} = {v}")

# 提取故障模式（F-001 / F-002 / F-003）
fault_pattern = re.compile(
    r"故障模式\s*(F-\d+)[：:]\s*([^\n]+)\s*\n"
    r"\s*症状[：:]\s*([^\n]+)\s*\n"
    r"\s*可能原因[：:]\s*\n"
    r"((?:\s*-\s*[^\n]+\n)+)"
    r"\s*维修方案[：:]\s*\n"
    r"((?:\s*S-\d+[：:]\s*[^\n]+\n)+)",
    re.MULTILINE
)

faults = []
for m in fault_pattern.finditer(text):
    fault_id, fault_name, symptom, causes_block, solutions_block = m.groups()

    causes = re.findall(r"-\s*(.+?)(?:\(parentComponent:\s*([^)]+)\))?\s*$", causes_block, re.MULTILINE)
    solutions = re.findall(r"S-(\d+)[：:]\s*(.+?)(?:（(.+?)）)?\s*$", solutions_block, re.MULTILINE)

    fault = {
        "id": fault_id,
        "name": fault_name.strip(),
        "symptom": symptom.strip(),
        "causes": [{"desc": c[0].strip(), "component": c[1].strip() if c[1] else None} for c in causes],
        "solutions": [{"id": f"S-{s[0]}", "desc": s[1].strip(), "detail": s[2].strip() if s[2] else None} for s in solutions],
    }
    faults.append(fault)

print(f"\n  发现故障模式: {len(faults)}")
for f in faults:
    print(f"    {f['id']}: {f['name']} → {len(f['causes'])} 个原因 / {len(f['solutions'])} 个方案")

# ===== 2. 构造三元组 =====
print("\n" + "=" * 60)
print("🔗 第 2 步：构造 (head, relation, tail) 三元组")
print("=" * 60)

triples = []

# 装备属性三元组
for attr_name, attr_val in attrs:
    triples.append((equip_model, "HAS_ATTRIBUTE", f"{attr_name}={attr_val}"))

# 故障三元组
for f in faults:
    triples.append((equip_model, "HAS_FAULT_MODE", f"{f['id']}:{f['name']}"))
    triples.append((f"{f['id']}:{f['name']}", "HAS_SYMPTOM", f["symptom"]))

    for c in f["causes"]:
        triples.append((f"{f['id']}:{f['name']}", "CAUSED_BY", c["desc"]))
        if c["component"]:
            triples.append((c["desc"], "LOCATED_IN_COMPONENT", c["component"]))

    for s in f["solutions"]:
        triples.append((f"{f['id']}:{f['name']}", "REPAIRED_BY", f"{s['id']}:{s['desc']}"))

print(f"  共生成三元组: {len(triples)}")
for h, r, t in triples[:10]:
    print(f"    ({h}) -[{r}]-> ({t})")

# ===== 3. 写入 Neo4j =====
print("\n" + "=" * 60)
print("💾 第 3 步：写入 Neo4j")
print("=" * 60)

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PWD))

# 清空旧数据（用于 PoC）
with driver.session() as session:
    session.run("MATCH (n) DETACH DELETE n")
    print("  ✅ 清空旧图谱")

# 创建节点并建立关系
with driver.session() as session:
    for h, r, t in triples:
        session.run("""
            MERGE (a:Entity {name: $head})
            MERGE (b:Entity {name: $tail})
            MERGE (a)-[:RELATES {type: $rel}]->(b)
        """, head=h, rel=r, tail=t)
    print(f"  ✅ 写入三元组完成")

# ===== 4. 验证 =====
print("\n" + "=" * 60)
print("🔍 第 4 步：查询验证")
print("=" * 60)

with driver.session() as session:
    # 统计
    n_nodes = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
    n_rels = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
    print(f"  图谱统计: {n_nodes} 节点, {n_rels} 关系")

    # 故障因果链查询
    print("\n  —— 故障因果链查询（Neo4j Browser 也能看）——")
    rows = session.run("""
        MATCH (fault:Entity)-[:CAUSED_BY]->(cause:Entity)
        MATCH (fault)-[:REPAIRED_BY]->(solution:Entity)
        RETURN fault.name AS fault, collect(DISTINCT cause.name) AS causes, collect(DISTINCT solution.name) AS solutions
        LIMIT 10
    """)
    for row in rows:
        print(f"    🚨 {row['fault']}")
        print(f"       原因: {row['causes']}")
        print(f"       方案: {row['solutions']}")

    # Cypher 查询（供 Neo4j Browser 使用）
    print("\n  —— 在 Neo4j Browser 中可运行这些 Cypher ——")
    print('    MATCH (n) RETURN n LIMIT 50;')
    print('    MATCH (f)-[r]->(s) WHERE f.name CONTAINS "故障" RETURN f,r,s LIMIT 25;')

driver.close()

print("\n" + "=" * 60)
print("🎉 Neo4j 管道验证完成！")
print("   打开 http://localhost:7474  （neo4j / eqkg2026）")
print("   在 Query 面板输入 MATCH (n) RETURN n LIMIT 50 查看图谱")
print("=" * 60)
