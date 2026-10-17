"""抽取主存（SQLite）—— 文档元数据 + 抽取运行 + 三元组快照 + 本体 Schema。

设计目标：
  1. 图谱消费可追溯：任何三元组都能追到 "哪个文档 + 哪次抽取"
  2. 支持重抽取：删某文档旧数据 → 重新抽 → MERGE 回 Neo4j
  3. 零安装：SQLite 是 Python 自带的，不需要额外装 PostgreSQL/MySQL
  4. 将来升级 PG/MySQL 只需换 settings.postgres.dsn，接口不变
  5. 本体约束落库：entity_types / relation_types / attribute_keys 三表 + 校验函数

六张表:
  documents     — 文档元数据（文件名、解析方式、text_len、上传时间）
  extract_runs  — 每次抽取（doc_id、method=rule|llm、耗时、状态）
  triples       — 三元组快照（head/hl/rel/tail/tl + 来源 run_id）
  entity_types  — 本体概念类（code、名称、层级、上位本体）
  relation_types — 本体关系（code、domain、range、约束）
  attribute_keys — 本体属性键（code、名称、所属类、数据类型、单位）
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Optional

from ontology import (
    ENTITY_TYPES, RELATION_TYPES, ATTRIBUTE_KEYS,
    validate_triple as ontology_validate,
)

# ---- 默认库位置 ----
_HERE = Path(__file__).parent
DEFAULT_DB = _HERE / "eqkg.db"


# ============================================================
# 连接管理
# ============================================================
@contextmanager
def get_conn(db_path: str | Path = DEFAULT_DB):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")   # 读写并发安全
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str | Path = DEFAULT_DB) -> None:
    """建表（幂等，重复调用安全）。"""
    with get_conn(db_path) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename    TEXT NOT NULL,
            parser_method TEXT NOT NULL DEFAULT 'unknown',  -- text | ocr | docx
            text_len    INTEGER NOT NULL DEFAULT 0,
            is_scanned  INTEGER NOT NULL DEFAULT 0,
            imported_at REAL NOT NULL,
            note        TEXT
        );

        CREATE TABLE IF NOT EXISTS extract_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id      INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            method      TEXT NOT NULL DEFAULT 'rule',       -- rule | llm | hybrid
            triple_count INTEGER NOT NULL DEFAULT 0,
            duration_s  REAL NOT NULL DEFAULT 0,
            status      TEXT NOT NULL DEFAULT 'ok',          -- ok | failed | merged
            run_at      REAL NOT NULL,
            error       TEXT
        );

        CREATE TABLE IF NOT EXISTS triples (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id      INTEGER NOT NULL REFERENCES extract_runs(id) ON DELETE CASCADE,
            head        TEXT NOT NULL,
            hl          TEXT NOT NULL,
            rel         TEXT NOT NULL,
            tail        TEXT NOT NULL,
            tl          TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_triples_head ON triples(head);
        CREATE INDEX IF NOT EXISTS idx_triples_tail ON triples(tail);
        CREATE INDEX IF NOT EXISTS idx_runs_doc     ON extract_runs(doc_id);

        -- 本体 Schema 三表
        CREATE TABLE IF NOT EXISTS entity_types (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT UNIQUE NOT NULL,      -- E01-01
            name_zh     TEXT NOT NULL,             -- 生物侦检装备
            neo4j_label TEXT NOT NULL,             -- E01_01
            level       TEXT NOT NULL,             -- 根节点 / 一级 / 二级
            parent      TEXT REFERENCES entity_types(code),  -- 上位本体
            definition  TEXT,
            examples    TEXT
        );

        CREATE TABLE IF NOT EXISTS relation_types (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT UNIQUE NOT NULL,      -- R-003
            name_zh     TEXT NOT NULL,             -- 采用
            name_en     TEXT NOT NULL,             -- adopts
            category    TEXT NOT NULL,             -- 属性与能力
            domain      TEXT NOT NULL,              -- JSON: ["E01"]
            range       TEXT NOT NULL,              -- JSON: ["E03"]
            description TEXT,
            example     TEXT
        );

        CREATE TABLE IF NOT EXISTS attribute_keys (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            code                 TEXT UNIQUE NOT NULL,   -- AT-001
            name_zh              TEXT NOT NULL,          -- 装备名称
            name_en              TEXT NOT NULL,          -- equipmentName
            applicable_concepts  TEXT NOT NULL,           -- JSON: ["E01", "E01-01"]
            data_type            TEXT NOT NULL DEFAULT 'TEXT',
            unit                 TEXT NOT NULL DEFAULT '',
            required             INTEGER NOT NULL DEFAULT 0,
            example              TEXT
        );
        """)


# ============================================================
# 文档元数据
# ============================================================
def ingest_document(
    filename: str,
    text_len: int,
    parser_method: str = "text",
    is_scanned: bool = False,
    note: str = "",
    db_path: str | Path = DEFAULT_DB,
) -> int:
    """登记一个新文档，返回 doc_id。"""
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO documents (filename, parser_method, text_len, is_scanned, imported_at, note)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (filename, parser_method, text_len, int(is_scanned), time.time(), note),
        )
        return cur.lastrowid


def list_documents(db_path: str | Path = DEFAULT_DB) -> list[dict]:
    """列出所有已导入文档 + 各文档的三元组总数。"""
    with get_conn(db_path) as conn:
        rows = conn.execute(
            """SELECT d.*,
                     COALESCE(SUM(er.triple_count), 0) AS total_triples,
                     MAX(er.run_at) AS last_run
               FROM documents d
               LEFT JOIN extract_runs er ON er.doc_id = d.id
               GROUP BY d.id
               ORDER BY d.imported_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


def get_document(doc_id: int, db_path: str | Path = DEFAULT_DB) -> Optional[dict]:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        return dict(row) if row else None


def delete_document(doc_id: int, db_path: str | Path = DEFAULT_DB, dry_run: bool = False) -> int:
    """删文档及其所有抽取结果。返回影响行数。

    注意：此操作不自动清理 Neo4j 里的节点/关系 —— 图谱节点可能被多个文档共享。
    """
    with get_conn(db_path) as conn:
        # 先查要删的数量
        doc = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        if not doc:
            return 0
        run_count = conn.execute("SELECT COUNT(*) FROM extract_runs WHERE doc_id=?", (doc_id,)).fetchone()[0]
        triple_count = conn.execute(
            """SELECT COUNT(*) FROM triples WHERE run_id IN
               (SELECT id FROM extract_runs WHERE doc_id=?)""",
            (doc_id,),
        ).fetchone()[0]

        affected = 1 + run_count + triple_count
        if dry_run:
            print(f"[dry-run] 将删除 doc_id={doc_id} ({doc['filename']}) + {run_count} runs + {triple_count} triples = 共 {affected} 行")
            return affected

        conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        # ON DELETE CASCADE 会联动删 extract_runs 和 triples
        return affected


# ============================================================
# 抽取运行 + 三元组快照
# ============================================================
def save_extract_run(
    doc_id: int,
    triples: Iterable[dict],
    method: str = "rule",
    duration_s: float = 0,
    db_path: str | Path = DEFAULT_DB,
) -> int:
    """存一次抽取运行 + 其所有三元组快照。返回 run_id。"""
    triples = list(triples)
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO extract_runs (doc_id, method, triple_count, duration_s, status, run_at)
               VALUES (?, ?, ?, ?, 'ok', ?)""",
            (doc_id, method, len(triples), duration_s, time.time()),
        )
        run_id = cur.lastrowid

        # 批量插入三元组
        if triples:
            conn.executemany(
                """INSERT INTO triples (run_id, head, hl, rel, tail, tl)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [(run_id, t["head"], t["hl"], t["rel"], t["tail"], t["tl"]) for t in triples],
            )
        return run_id


def get_triples_for_doc(doc_id: int, db_path: str | Path = DEFAULT_DB) -> list[dict]:
    """取某文档最新一次抽取的所有三元组。"""
    with get_conn(db_path) as conn:
        row = conn.execute(
            """SELECT id FROM extract_runs WHERE doc_id=? ORDER BY run_at DESC LIMIT 1""",
            (doc_id,),
        ).fetchone()
        if not row:
            return []
        rows = conn.execute(
            """SELECT head, hl, rel, tail, tl FROM triples WHERE run_id=?""",
            (row["id"],),
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_triples(db_path: str | Path = DEFAULT_DB) -> list[dict]:
    """取所有文档最新抽取结果的合并三元组（去重）。"""
    with get_conn(db_path) as conn:
        rows = conn.execute(
            """SELECT DISTINCT t.head, t.hl, t.rel, t.tail, t.tl
               FROM triples t
               WHERE t.run_id IN (
                   SELECT MAX(id) FROM extract_runs GROUP BY doc_id
               )"""
        ).fetchall()
        return [dict(r) for r in rows]


# ============================================================
# 统计
# ============================================================
def stats(db_path: str | Path = DEFAULT_DB) -> dict:
    with get_conn(db_path) as conn:
        return {
            "documents": conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
            "extract_runs": conn.execute("SELECT COUNT(*) FROM extract_runs").fetchone()[0],
            "triples": conn.execute("SELECT COUNT(*) FROM triples").fetchone()[0],
        }


# ============================================================
# 本体 Schema 种子数据（从 ontology.py 自动加载）
# ============================================================
def seed_ontology(db_path: str | Path = DEFAULT_DB, force: bool = False) -> dict:
    """把 ontology.py 里的 56 实体/20 关系/101 属性 写入 SQLite schema 三表。

    Args:
        force: True 时清空旧数据再重写（迁移时用）

    Returns:
        dict: {"entity_types": N, "relation_types": N, "attribute_keys": N}
    """
    with get_conn(db_path) as conn:
        if force:
            conn.execute("DELETE FROM attribute_keys")
            conn.execute("DELETE FROM relation_types")
            conn.execute("DELETE FROM entity_types")

        # entity_types
        existing = conn.execute("SELECT COUNT(*) FROM entity_types").fetchone()[0]
        if existing == 0 or force:
            conn.executemany(
                """INSERT OR REPLACE INTO entity_types
                   (code, name_zh, neo4j_label, level, parent, definition, examples)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [(e.code, e.name_zh, e.neo4j_label, e.level,
                  e.parent, e.definition, e.examples)
                 for e in ENTITY_TYPES.values()],
            )

        # relation_types
        existing = conn.execute("SELECT COUNT(*) FROM relation_types").fetchone()[0]
        if existing == 0 or force:
            conn.executemany(
                """INSERT OR REPLACE INTO relation_types
                   (code, name_zh, name_en, category, domain, range, description, example)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [(r.code, r.name_zh, r.name_en, r.category,
                  json.dumps(r.domain, ensure_ascii=False),
                  json.dumps(r.range, ensure_ascii=False),
                  r.description, r.example)
                 for r in RELATION_TYPES.values()],
            )

        # attribute_keys
        existing = conn.execute("SELECT COUNT(*) FROM attribute_keys").fetchone()[0]
        if existing == 0 or force:
            conn.executemany(
                """INSERT OR REPLACE INTO attribute_keys
                   (code, name_zh, name_en, applicable_concepts, data_type, unit, required, example)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [(a.code, a.name_zh, a.name_en,
                  json.dumps(a.applicable_concepts, ensure_ascii=False),
                  a.data_type, a.unit, int(a.required), a.example)
                 for a in ATTRIBUTE_KEYS.values()],
            )

        return {
            "entity_types": conn.execute("SELECT COUNT(*) FROM entity_types").fetchone()[0],
            "relation_types": conn.execute("SELECT COUNT(*) FROM relation_types").fetchone()[0],
            "attribute_keys": conn.execute("SELECT COUNT(*) FROM attribute_keys").fetchone()[0],
        }


# ============================================================
# 三元组本体校验 + 过滤
# ============================================================
def validate_and_filter_triples(
    triples: Iterable[dict],
    db_path: str | Path = DEFAULT_DB,
) -> tuple[list[dict], list[dict]]:
    """批量校验三元组，拆分为 (合法, 违规) 两组。

    违规项返回额外字段 violation_reason。

    Usage:
        valid, invalid = validate_and_filter_triples(triples)
        if invalid:
            for t in invalid:
                print(f"  ❌ {t['violation_reason']}: {t['hl']} —[{t['rel']}]→ {t['tl']}")
    """
    valid, invalid = [], []
    for t in triples:
        hl, rel, tl = t.get("hl", ""), t.get("rel", ""), t.get("tl", "")

        # 实体 code 提取：hl 可能是 "E01-01 生物侦检装备" 或 "E01_01" 或 "Equipment"
        head_code = _extract_concept_code(hl)
        tail_code = _extract_concept_code(tl)

        # 如果实体 code 提取失败（旧粗粒度本体标签），记违规
        if not head_code or not tail_code:
            t2 = dict(t)
            t2["violation_reason"] = f"实体概念类未对齐本体 (hl={hl}, tl={tl})"
            invalid.append(t2)
            continue

        if not ontology_validate(head_code, rel, tail_code):
            t2 = dict(t)
            rel_def = None
            # 尝试找关系定义给更好的报错
            invalid.append(t2)
            continue

        valid.append(t)

    return valid, invalid


def _extract_concept_code(hl_or_tl: str) -> Optional[str]:
    """从 hl/tl 字段提取概念类 code（兼容多种格式）。

    可能的输入格式:
      "E01-01 生物侦检装备"  → "E01-01"
      "E01_01"               → "E01-01"  (Neo4j label 格式)
      "E01-01"               → "E01-01"
      "Equipment"            → None  (旧粗粒度本体，无 code)
    """
    import re
    if not hl_or_tl:
        return None
    # 先尝试 E01-01 或 E01_01 这种格式
    m = re.search(r"(E\d{2}[-_]\d{2}|E\d{2})", hl_or_tl)
    if m:
        code = m.group(1).replace("_", "-")  # 统一成 E01-01
        if code in ENTITY_TYPES:
            return code
        # 可能是一级类（E01），也可能有效
        return code
    return None


# ============================================================
# 启动时自动建表 + seed
# ============================================================
init_db()
seed_ontology()


if __name__ == "__main__":
    print(f"📦 SQLite: {DEFAULT_DB}")
    print(f"📊 数据: {stats()}")
    print(f"📐 本体: {seed_ontology()}")

    # 测试校验
    test_triples = [
        {"head": "DNBSEQ-E25RS", "hl": "E01-01 生物侦检装备",
         "rel": "adopts", "tail": "cPAS测序技术", "tl": "E03-01 装备原理"},
        {"head": "DNBSEQ-E25RS", "hl": "E01-01 生物侦检装备",
         "rel": "adopts", "tail": "防疫任务", "tl": "E07-01 防疫任务"},  # ❌ 违规
        {"head": "测序仪", "hl": "Equipment", "rel": "HAS_COMPONENT",   # ❌ 旧粗粒度
         "tail": "电源模块", "tl": "Component"},
    ]
    valid, invalid = validate_and_filter_triples(test_triples)
    print(f"\n🧪 校验测试: {len(valid)} 合法, {len(invalid)} 违规")
    for t in invalid:
        print(f"  ❌ {t.get('violation_reason', 'domain/range 约束不满足')}: [{t['hl']}] {t['head']} —[{t['rel']}]→ {t['tail']} [{t['tl']}]")
