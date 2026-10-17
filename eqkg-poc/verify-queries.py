"""补 Cypher 查询验证（修复关系类型查询错误）"""
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "eqkg2026"))

with driver.session() as s:
    print("=== 图谱验证查询 ===\n")

    # 1. 节点/关系统计
    n = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
    r = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
    print(f"1) 总统计: {n} 节点, {r} 关系")

    # 2. 装备 → 故障 → 原因 → 组件（完整因果链）
    print("\n2) 装备→故障→原因→组件 因果链:")
    rows = s.run("""
        MATCH (equip:Entity)-[:RELATES {type:'HAS_FAULT_MODE'}]->(fault)
        MATCH (fault)-[:RELATES {type:'CAUSED_BY'}]->(cause)
        OPTIONAL MATCH (cause)-[:RELATES {type:'LOCATED_IN_COMPONENT'}]->(comp)
        RETURN equip.name AS equip, fault.name AS fault,
               collect(DISTINCT cause.name + COALESCE('  (' + comp.name + ')', '')) AS causes
        ORDER BY fault.name
    """)
    for row in rows:
        print(f"   🚛 {row['equip']}  ⚠  {row['fault']}")
        for c in row['causes']:
            print(f"      └─ {c}")

    # 3. 故障 → 维修方案
    print("\n3) 故障→维修方案:")
    rows = s.run("""
        MATCH (fault:Entity)-[:RELATES {type:'REPAIRED_BY'}]->(sol)
        RETURN fault.name AS fault, collect(DISTINCT sol.name) AS sols
        ORDER BY fault.name
    """)
    for row in rows:
        print(f"   🔧 {row['fault']} → {row['sols']}")

    # 4. 装备属性
    print("\n4) 装备属性:")
    rows = s.run("""
        MATCH (equip:Entity)-[:RELATES {type:'HAS_ATTRIBUTE'}]->(attr)
        RETURN equip.name AS equip, collect(attr.name) AS attrs
    """)
    for row in rows:
        print(f"   🛡 {row['equip']}: {row['attrs']}")

driver.close()
print("\n✅ Neo4j Browser 打开 http://localhost:7474 (neo4j / eqkg2026)")
print("   在 Query 面板运行: MATCH (n)-[r]->(m) RETURN n,r,m LIMIT 50")
