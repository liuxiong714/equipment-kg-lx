# 装备知识图谱 PoC（equipment-kg-lx）

> 本地 Ollama LLM（qwen2.5:7b）+ Neo4j 图数据库，从装备说明书 PDF 抽取实体/属性/关系，构建可查询的语义知识图谱。
> 项目代号 eqkg-poc，单进程 Flask UI，Windows + WSL2 Docker 环境。

## 技术栈

| 组件 | 版本 | 用途 |
|------|------|------|
| Python | 3.12 | 运行时 |
| Flask | 3.x | Web UI + REST API |
| Neo4j | 5.23+ | 图数据库（Docker 容器） |
| py2neo / neo4j driver | 5.x | Neo4j Python 客户端 |
| Ollama | 本地 | qwen2.5:7b（LLM Text2Cypher 兜底，CPU 下较慢） |
| PyMuPDF (fitz) | 1.24+ | PDF 文字层提取 |
| Tesseract OCR | 5.4.0 | 扫描件 PDF → 图片 OCR（chi_sim+eng） |
| python-docx | 1.x | Word 文档解析 |
| SQLite | Python 自带 | 抽取主存（documents / extract_runs / triples） |
| pydantic-settings | 2.x | 配置中心（可选，未装时 fallback 到 os.environ） |

## 目录结构

```
sfzb/
├── eqkg-poc/                    # PoC 主包
│   ├── qa-flask-app.py          # Flask Web UI + REST 路由
│   ├── qa_engine.py             # 问答引擎：规则模板 + LLM Text2Cypher
│   ├── eqkg_extractor.py        # 规则抽取核心：属性/部件/故障/功能
│   ├── ontology.py              # 本体定义：EntityType / RelationType 枚举 + 白名单
│   ├── config.py                # 配置中心：Neo4j / Ollama / App / Postgres
│   ├── persist.py               # SQLite 抽取主存：documents / extract_runs / triples
│   ├── parsers/                 # 文档解析策略层
│   │   ├── base.py              # BaseParser + @register_parser 装饰器 + get_parser()
│   │   ├── pdf_parser.py        # PDF 文字层（PyMuPDF）
│   │   ├── docx_parser.py       # Word 文档（python-docx）
│   │   └── ocr_parser.py        # 扫描件智能解析：smart_parse_pdf() 文字层→OCR fallback
│   ├── providers/               # LLM Provider 抽象层
│   │   ├── base.py              # LLMProvider + get_provider() + NullProvider 兜底
│   │   └── ollama_provider.py   # OllamaProvider / OpenAIProvider
│   └── tessdata/                # 本地 Tesseract 语言包（chi_sim + eng + osd）
├── .env.example                 # 环境变量模板（复制为 .env 后按需改）
├── README.md
├── CHANGELOG.md
└── docs/FEATURES.md             # 功能清单与路线图
```

## 快速开始

### 0. 前置条件

- **WSL2 + Docker**: 本项目的 Neo4j 跑在 WSL2 Ubuntu-22.04 的 Docker 里
- **Ollama**: 已装且部署了 qwen2.5:7b（CPU 最实用）和 qwen3.5:4b（有 thinking，CPU 禁用）
- **Python 3.12**: `py -0p` 应能看到 3.12
- **Tesseract OCR 5.4.0**: `C:\Program Files\Tesseract-OCR\tesseract.exe`（chi_sim 语言包在 `eqkg-poc/tessdata/`）

### 1. 启动 Neo4j（WSL2）

```bash
# WSL2 终端
sudo dockerd &          # 如果 daemon 没跑
docker start neo4j-eqkg  # 容器名，首次创建见下文

# 首次创建（只需一次）
docker run -d --name neo4j-eqkg -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/eqkg2026 \
  -e 'NEO4J_PLUGINS=["apoc","graph-data-science"]' \
  -v neo4j-eqkg-data:/data neo4j:5-community
```

### 2. 安装依赖（Windows PowerShell）

```powershell
# 清华镜像（GitHub 被墙时必备）
py -3.12 -m pip install neo4j requests pymupdf python-docx -i https://pypi.tuna.tsinghua.edu.cn/simple
py -3.12 -m pip install pytesseract pillow -i https://pypi.tuna.tsinghua.edu.cn/simple
py -3.12 -m pip install pydantic-settings flask -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 3. 启动 Flask

```powershell
cd E:\linux\trae_project\sfzb
py -3.12 -u eqkg-poc/qa-flask-app.py
# 打开 http://localhost:5000
```

### 4. 导入文档

1. 打开 http://localhost:5000 → **📥 文档导入** Tab
2. 选择装备 PDF（文字层或扫描件均可）
3. 预览抽取结果 → ✅ **确认导入到知识图谱**
4. 也可以命令行：
   ```powershell
   py -3.12 -c "from eqkg_extractor import extract_from_pdf, merge_triples; \
       from neo4j import GraphDatabase; \
       from config import settings, neo4j_auth; \
       r = extract_from_pdf(r'E:\path\to\equip.pdf'); \
       d = GraphDatabase.driver(settings.neo4j.uri, auth=neo4j_auth()); \
       print(merge_triples(d, r['triples'])); d.close()"
   ```

### 5. 问答

```powershell
# 命令行
py -3.12 -u eqkg-poc/qa_engine.py "测序仪有哪些部件"
# 或 Web UI → ❓ 问答 Tab
```

### 6. Neo4j Browser

http://localhost:7474 （neo4j / eqkg2026）

## 当前图谱（2026-10-17）

6 台装备 PDF 全导入，87 三元组覆盖：

| 装备 | 来源 | 解析方式 | 三元组 |
|------|------|----------|--------|
| DNBSEQ-E25RS& 便携式基因测序仪 | 文字层 | PyMuPDF | 48 |
| DNBSEQ-E25ARS 核酸检测 | 文字层 | PyMuPDF | 22 |
| 全波长多功能酶标分析仪 | 扫描件 | Tesseract OCR | 12 |
| 荧光计定量仪 | 扫描件 | Tesseract OCR | 4 |
| 全自动分子 POCT 分析仪 CentriDx 200 | 扫描件 | Tesseract OCR | 1 |
| 台式扫描电镜 | 扫描件 | Tesseract OCR | 0 |

图谱统计：
```
节点: Equipment × 6, Component × 21, Function × 21, Fault × 16, Attribute × 1
关系: HAS_COMPONENT × 24, PERFORMS_FUNCTION × 21, HAS_FAULT_MODE × 16, HAS_ATTRIBUTE × 1
```

## 架构设计

```
用户上传 PDF
     │
     ▼
┌─────────────────────────────────────┐
│ parsers/           文档解析策略层     │
│  PdfParser    → PyMuPDF 文字层       │
│  DocxParser   → python-docx          │
│  OcrPdfParser → 扫描件 → Tesseract   │
│  smart_parse_pdf()  自动 fallback    │
└─────────────────────────────────────┘
     │ text: str
     ▼
┌─────────────────────────────────────┐
│ eqkg_extractor.py  规则抽取核心       │
│  COMPONENT_PATTERNS / ATTR_PATTERNS  │
│  FAULT_WORDS / REPAIR_WORDS          │
│  → list[{head, hl, rel, tail, tl}]   │
└─────────────────────────────────────┘
     │ triples
     ▼
┌─────────────────────────────────────┐
│ persist.py  SQLite 抽取主存          │
│  documents / extract_runs / triples  │
│  可追溯 / 可重抽 / dry_run 删除       │
└─────────────────────────────────────┘
     │ triples
     ▼
┌─────────────────────────────────────┐
│ Neo4j  图谱消费（MERGE 去重）        │
│  qa_engine.py  规则模板 + LLM 兜底   │
└─────────────────────────────────────┘
```

## 本体定义

```
实体 (EntityType):
  Equipment / Component / Fault / Function / Attribute / Solution / Sensor / Reagent / Manufacturer / Document

关系 (RelationType):
  HAS_COMPONENT / HAS_ATTRIBUTE / PERFORMS_FUNCTION / HAS_FAULT_MODE
  USES_REAGENT / HAS_SENSOR / MANUFACTURED_BY
  REPAIRED_BY / CAUSES / LOCATED_IN / REQUIRES_COMPONENT
  IS_A / PART_OF / DESCRIBED_IN
```

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/upload` | 上传 PDF → 返回抽取预览（含 doc_id） |
| POST | `/api/commit` | `{doc_id}` → MERGE 进 Neo4j |
| POST | `/api/ask` | `{question, use_llm}` → 问答结果 |
| GET | `/api/overview` | 图谱统计（节点标签/关系类型/总数） |
| GET | `/api/documents` | 已导入文档列表 + 三元组数 |
| DELETE | `/api/documents/<id>?dry_run=1` | 删除某文档抽取历史 |

## 配置

`.env`（从 `.env.example` 复制）或环境变量：

```bash
# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=eqkg2026

# Ollama
OLLAMA_URL=http://localhost:11434
LLM_MODEL=qwen2.5:7b

# Postgres（可选，暂不启用）
# POSTGRES_DSN=postgresql://user:pass@localhost:5432/eqkg
```

## 已知局限

| 问题 | 根因 | 解决方向 |
|------|------|----------|
| POCT 分析仪只抽 1 三元组 | 扫描件文字太少（969 字） | 提高 OCR dpi 到 300 / 增加页上限 |
| 扫描电镜抽 0 三元组 | OCR 只识别出型号标题，无结构内容 | 彩页型 PDF 需要更宽松的规则 / 加 LLM 抽取兜底 |
| OCR 后装备型号还是文件名 | `detect_equipment_name()` 只查首页显式字段，OCR 文字层里型号分散 | LLM 抽取时直接从 OCR 输出识别型号 |
| LLM CPU 推理不可用 | qwen2.5:7b 纯 CPU ≈ 0.02 tok/s + Ollama 反复卸载 | GPU 就绪后启用 Provider 层 |
| 故障节点有噪音 | FAULT_WORDS 误抓免责声明 | 故障关键词 + 部件名联动过滤 |

## 升级路线图

详见 [docs/FEATURES.md](docs/FEATURES.md)

## 许可证

MIT
