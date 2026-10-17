# Features & Roadmap

装备知识图谱 PoC 功能清单与路线图。

---

## 当前功能（v0.2.0 已实现）

### ✅ 数据接入

| 功能 | 说明 | 状态 |
|------|------|------|
| PDF 文字层解析 | PyMuPDF (fitz) | ✅ |
| DOCX 解析 | python-docx | ✅ |
| 扫描件 OCR | Tesseract 5.4.0，chi_sim + eng | ✅ |
| 图片 OCR | .png/.jpg/.tif/.bmp 直接识别 | ✅ |
| 智能 PDF 解析 | 文字层 → 空则自动 OCR fallback | ✅ |
| Parser 策略层 | BaseParser + @register_parser + get_parser() | ✅ |
| OCR 本地语言包 | eqkg-poc/tessdata/（免安装目录） | ✅ |

### ✅ 知识抽取

| 功能 | 说明 | 状态 |
|------|------|------|
| 部件抽取 | COMPONENT_PATTERNS 正则（控制单元/电源/传感器...） | ✅ |
| 属性抽取 | ATTR_PATTERNS 正则（体积/重量/电压/功率/型号...） | ✅ |
| 故障模式抽取 | FAULT_WORDS 正则（故障/失效/异常/E-xxx 错误码...） | ✅ |
| 维修方案抽取 | REPAIR_WORDS 正则（维修/更换/校准/重置...） | ✅ |
| 功能抽取 | 中文句式正则（"可用于"/"主要功能"） | ✅ |
| 装备型号识别 | PDF 首页显式字段 → 大厂型号前缀 → 文件名退化 | ✅ |
| 本体安全校验 | MERGE 前检查 label/rel 在白名单 | ✅ |

### ✅ 知识融合

| 功能 | 说明 | 状态 |
|------|------|------|
| Neo4j MERGE 去重 | 不破坏已有节点，只补充新关系 | ✅ |
| SQLite 抽取主存 | documents / extract_runs / triples 三表 | ✅ |
| 可追溯 | 任何三元组 → doc_id → 哪篇文档 + 哪次抽取 | ✅ |
| dry_run 删除 | `delete_document(doc_id, dry_run=True)` 先报行数 | ✅ |
| 重抽取支持 | 删旧 run → 重新抽 → MERGE 回 Neo4j | ✅ |

### ✅ 知识消费

| 功能 | 说明 | 状态 |
|------|------|------|
| 规则模板问答 | 5 组模板，瞬间命中（测序仪有哪些部件？） | ✅ |
| LLM Text2Cypher 兜底 | Ollama /api/generate，CPU 下较慢 | ✅ |
| Cypher 安全执行 | 禁写 + 强制 LIMIT | ✅ |
| Flask Web UI | 三 Tab：问答 / 导入 / 图谱预览 | ✅ |
| REST API | upload / commit / ask / overview / documents | ✅ |
| Neo4j Browser 嵌入 | iframe http://localhost:7474 | ✅ |

### ✅ 架构

| 功能 | 说明 | 状态 |
|------|------|------|
| 本体集中定义 | ontology.py: EntityType / RelationType 枚举 | ✅ |
| 配置中心 | config.py: pydantic-settings + os.environ fallback | ✅ |
| LLM Provider 抽象 | OllamaProvider / OpenAIProvider / NullProvider | ✅ |
| 项目级 tessdata | chi_sim + eng + osd 放 eqkg-poc/tessdata/ | ✅ |
| .gitignore 规范化 | SQLite / llm-graph-builder / .env | ✅ |

---

## 已知局限（当前版本）

| # | 问题 | 影响 | 根因 |
|---|------|------|------|
| L1 | 故障节点有噪音 | 16 个 Fault 里有安全免责声明 | FAULT_WORDS 误抓，未联动部件名过滤 |
| L2 | OCR 装备型号识别差 | 扫描件装备名退化为文件名 | detect_equipment_name() 只查显式字段 |
| L3 | POCT/扫描电镜抽取太少 | POCT 1 三元组，扫描电镜 0 | OCR 后文字量不足 / 规则不够宽松 |
| L4 | LLM CPU 不可用 | Text2Cypher 兜底默认关 | qwen2.5:7b 纯 CPU ≈ 0.02 tok/s + Ollama 卸载 |
| L5 | 无增量抽取 | 重抽 = 删旧 run + 全量重灌 | 规则抽取本身无增量概念 |
| L6 | 无实体消歧 | "测序仪" 不等于 "DNBSEQ-E25RS" | 未做同义词归一 + term normalizer |
| L7 | 数据库结构注释不足 | SQLite 三表无字段注释 | 建表脚本应补 COMMENT |

---

## 路线图

### v0.3.0 — 质量提升（1-2 天，规则侧优化）

| 功能 | 优先级 | 说明 |
|------|--------|------|
| 故障质量修复 | **P0** | FAULT_WORDS 句子必须同时匹配 COMPONENT_PATTERNS 里的部件名，否则丢弃 |
| 装备型号标准化 | **P0** | OCR 后补正则：`re.search(r"型号[：:]\s*(\S+)", text[:5000])` + `RE_MODEL_PREFIXES` 扩展 |
| OCR 后二次清洗 | **P1** | OCR 文本去乱码、合并被换行截断的句子、过滤页码/页眉页脚 |
| Flask 上传支持 .docx | **P1** | 路由已经支持 ext 判断，只需 `ALLOWED_EXT += {docx}` |
| SQLite 表结构注释 | **P2** | `CREATE TABLE` 后 `COMMENT ON COLUMN` |

### v0.4.0 — 本体工程（2-3 天）

| 功能 | 优先级 | 说明 |
|------|--------|------|
| CCO 上层本体对齐 | **P0** | 克隆 CommonCoreOntology，装备子类挂在 CCO 的 Equipment 下 |
| 装备子类体系 | **P1** | Sequencer / Analyzer / Microscope / Spectrometer 等 |
| 同义词归一表 | **P1** | SQLite 加 `synonyms` 表：("测序仪", "DNA测序仪", "基因测序仪") → Equipment |
| 实体消歧 | **P2** | 同一装备不同型号 → `IS_A` 关系 + `PART_OF` 层级 |

### v0.5.0 — LLM 增强（需 GPU，3-5 天）

| 功能 | 优先级 | 说明 |
|------|--------|------|
| LLM 抽取管道 | **P0** | Provider 层 + JSON Schema 强约束输出 + 分级模型（短文本轻量/长文本强） |
| LLM vs 规则融合 | **P0** | 规则先抽 → LLM 补充漏网之鱼 → 结果融合去重 |
| LLM Text2Cypher 流式 | **P1** | Provider.stream_generate() → 逐 token 输出 |
| 反馈闭环 | **P2** | LLM 抽取结果人工审核 → 存入 `llm_feedback` 表 → 提示优化 |

### v1.0.0 — 生产就绪（一周+）

| 功能 | 优先级 | 说明 |
|------|--------|------|
| PostgreSQL 替换 SQLite | **P0** | `settings.postgres.dsn` 填了自动切，persist.py 底层换 psycopg |
| FastAPI 重构 | **P1** | 保持 API 不变，异步 + 类型安全 + OpenAPI 文档 |
| React 前端 | **P1** | 图谱可视化（Sigma.js / Cytoscape）+ 文档管理 + 审核流 |
| Redis + Celery 异步队列 | **P2** | 长文档抽取放后台，前端轮询状态 |
| Docker Compose 一键起 | **P2** | `docker compose up -d` 起 Neo4j + FastAPI + Worker + Ollama |
| 单元测试 | **P0** | pytest + 覆盖 ontology/parsers/persist/qa_engine ≥ 80% |

---

## 功能-架构映射

```
                 ┌─────────────────────────────────────┐
                 │  docs/FEATURES.md  功能清单         │
                 └──────────────────┬──────────────────┘
                                    │ 对应到
                 ┌──────────────────▼──────────────────┐
                 │  eqkg-poc/                          │
┌─────────────┐  │  ontology.py  本体定义              │
│ v0.3.0      │  │  config.py    配置中心              │
│ 故障修复     │  │  parsers/    文档解析策略层         │
│ 型号标准化   │  │  providers/  LLM Provider 抽象      │
└──────┬──────┘  │  persist.py  SQLite 抽取主存        │
       │         │  eqkg_extractor.py  规则抽取核心    │
       └────────►│  qa_engine.py  问答引擎             │
                 │  qa-flask-app.py  Web UI + REST     │
                 └──────────────┬──────────────────────┘
                                │ 消费
                 ┌──────────────▼──────────────────────┐
                 │  Neo4j 5.23  图数据库              │
                 └─────────────────────────────────────┘
```

---

## 升级决策记录

| 决策 | 理由 | 日期 |
|------|------|------|
| SQLite 而非 PostgreSQL 做主存 | Python 自带零安装，POC 阶段够用；切 PG 只改配置 | 2026-10-17 |
| OllamaProvider + NullProvider | CPU 禁用 LLM 时静默降级，将来 GPU 启用零代码改动 | 2026-10-17 |
| OCR 语言包放项目本地 | Program Files 写权限沙箱拦截，本地 tessdata 随仓库走 | 2026-10-17 |
| smart_parse_pdf() 函数 | Flask 路由只调一个入口，文字层/OCR 内部自动切换 | 2026-10-17 |
| 本体白名单硬校验 | MERGE 前过滤，防止脏数据进 Neo4j | 2026-10-17 |
| Tesseract OCR 而非 PaddleOCR | 已装且效果足够；PaddleOCR 需 PyTorch 2GB+ 额外依赖 | 2026-10-17 |
