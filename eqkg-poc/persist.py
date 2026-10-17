"""抽取主存（SQLite）—— 文档元数据 + 抽取运行 + 三元组快照。

设计目标：
  1. 图谱消费可追溯：任何三元组都能追到 "哪个文档 + 哪次抽取"
  2. 支持重抽取：删某文档旧数据 → 重新抽 → MERGE 回 Neo4j
  3. 零安装：SQLite 是 Python 自带的，不需要额外装 PostgreSQL/MySQL
  4. 将来升级 PG/MySQL 只需换 settings.postgres.dsn，接口不变

三张表:
  documents    — 文档元数据（文件名、解析方式、text_len、上传时间）
  extract_runs — 每次抽取（doc_id、method=rule|llm、耗时、状态）
  triples      — 三元组快照（head/hl/rel/tail/tl + 来源 run_id）
"""
from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Optional

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
# 启动时自动建表
# ============================================================
init_db()


if __name__ == "__main__":
    print(f"📦 SQLite: {DEFAULT_DB}")
    print(f"📊 {stats()}")
