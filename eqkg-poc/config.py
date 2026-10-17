"""装备知识图谱配置中心。

用法:
    from config import settings
    print(settings.neo4j.uri)
    print(settings.ollama.model)

环境变量优先 → .env 文件 → 默认值。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

try:
    from pydantic import BaseModel, Field
    from pydantic_settings import BaseSettings, SettingsConfigDict

    _HAS_PYDANTIC_V2 = True
except ImportError:  # fallback: 裸 dataclass + os.environ
    _HAS_PYDANTIC_V2 = False

    class _BaseModel:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

    class BaseSettings(_BaseModel):
        def model_post_init(self, __context):
            pass


# ============================================================
# 子配置
# ============================================================
class Neo4jSettings(_BaseModel if not _HAS_PYDANTIC_V2 else object):
    uri: str = "bolt://127.0.0.1:7687"
    user: str = "neo4j"
    password: str = "eqkg2026"


class OllamaSettings(_BaseModel if not _HAS_PYDANTIC_V2 else object):
    url: str = "http://localhost:11434"
    model: str = "qwen2.5:7b"  # 无 thinking，CPU 下最实用


class PostgresSettings(_BaseModel if not _HAS_PYDANTIC_V2 else object):
    """Phase 5 引入的抽取主存（空串 = 暂不启用）"""
    dsn: str = ""  # 例: postgresql://user:pass@localhost:5432/eqkg
    enabled: bool = False


class AppSettings(_BaseModel if not _HAS_PYDANTIC_V2 else object):
    host: str = "0.0.0.0"
    port: int = 5000
    max_upload_mb: int = 50
    allowed_extensions: tuple[str, ...] = ("pdf", "docx", "txt")


# ============================================================
# Settings 主类
# ============================================================
if _HAS_PYDANTIC_V2:
    from pydantic import BaseModel as _BM, Field as _F

    class Neo4jSettings(_BM):
        uri: str = _F(default="bolt://127.0.0.1:7687", alias="NEO4J_URI")
        user: str = _F(default="neo4j", alias="NEO4J_USER")
        password: str = _F(default="eqkg2026", alias="NEO4J_PASSWORD")

    class OllamaSettings(_BM):
        url: str = _F(default="http://localhost:11434", alias="OLLAMA_URL")
        model: str = _F(default="qwen2.5:7b", alias="LLM_MODEL")

    class PostgresSettings(_BM):
        dsn: str = _F(default="", alias="POSTGRES_DSN")
        enabled: bool = _F(default=False, alias="POSTGRES_ENABLED")

    class AppSettings(_BM):
        host: str = "0.0.0.0"
        port: int = 5000
        max_upload_mb: int = 50
        allowed_extensions: tuple[str, ...] = ("pdf",)

    class Settings(BaseSettings):
        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            case_sensitive=False,
            extra="ignore",
        )

        neo4j: Neo4jSettings = Neo4jSettings()
        ollama: OllamaSettings = OllamaSettings()
        postgres: PostgresSettings = PostgresSettings()
        app: AppSettings = AppSettings()

else:
    class Settings:
        """pydantic 未安装时的极简 fallback"""

        def __init__(self):
            self.neo4j = Neo4jSettings(
                uri=os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687"),
                user=os.environ.get("NEO4J_USER", "neo4j"),
                password=os.environ.get("NEO4J_PASSWORD", "eqkg2026"),
            )
            self.ollama = OllamaSettings(
                url=os.environ.get("OLLAMA_URL", "http://localhost:11434"),
                model=os.environ.get("LLM_MODEL", "qwen2.5:7b"),
            )
            pg_dsn = os.environ.get("POSTGRES_DSN", "")
            self.postgres = PostgresSettings(
                dsn=pg_dsn,
                enabled=bool(pg_dsn and os.environ.get("POSTGRES_ENABLED", "").lower() in ("1", "true", "yes")),
            )
            self.app = AppSettings()


settings = Settings()


# ============================================================
# 便捷函数
# ============================================================
def neo4j_auth() -> tuple[str, str]:
    return settings.neo4j.user, settings.neo4j.password


def ensure_pydantic() -> bool:
    """Phase 6 前不用装 pydantic 也能跑。Phase 5 PostgreSQL 主存化时建议升级。"""
    return _HAS_PYDANTIC_V2


# ============================================================
# 启动时打印一次配置（脱敏）
# ============================================================
if __name__ == "__main__":
    pwd = settings.neo4j.password
    masked = pwd[:2] + "***" + pwd[-1:] if len(pwd) > 4 else "***"
    print(f"Neo4j : {settings.neo4j.uri}  ({settings.neo4j.user}/{masked})")
    print(f"Ollama: {settings.ollama.url}  model={settings.ollama.model}")
    print(f"Postgres enabled: {settings.postgres.enabled}  dsn={'(空)' if not settings.postgres.dsn else settings.postgres.dsn}")
    print(f"Flask : {settings.app.host}:{settings.app.port}  upload≤{settings.app.max_upload_mb}MB")
