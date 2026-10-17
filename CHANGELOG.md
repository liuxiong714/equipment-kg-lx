# Changelog

所有重要变更记录在此。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [v0.2.0] — 2026-10-17

### 新增

- **本体集中定义** (`eqkg-poc/ontology.py`)
  - `EntityType`: 10 个装备领域实体枚举（Equipment / Component / Fault / Function / Attribute / Solution / Sensor / Reagent / Manufacturer / Document）
  - `RelationType`: 14 个关系枚举 + 中文标签 + 安全白名单 `ALLOWED_LABELS` / `ALLOWED_RELATIONS`
  - MERGE 写入时本体外标签/关系自动跳过

- **配置中心** (`eqkg-poc/config.py`)
  - pydantic-settings 多子配置：Neo4jSettings / OllamaSettings / PostgresSettings / AppSettings
  - 无 pydantic 时 fallback 到 os.environ，零依赖也能跑
  - `.env.example` 作为模板
  - qa_engine / qa-flask-app 硬编码全部迁移到 config

- **Parser 策略层** (`eqkg-poc/parsers/`)
  - `BaseParser` 抽象基类 + `@register_parser` 装饰器全局注册表
  - `PdfParser` PyMuPDF 文字层、`DocxParser` python-docx、`ImageParser` Tesseract
  - `OcrPdfParser` 扫描件 PDF 走 OCR + `smart_parse_pdf()` 文字层→OCR 自动 fallback
  - 注册扩展名：.pdf / .docx / .png / .jpg / .jpeg / .tif / .tiff / .bmp

- **LLM Provider 抽象层** (`eqkg-poc/providers/`)
  - `LLMProvider` 抽象基类 + `get_provider()` 工厂 + `NullProvider` CPU 禁用兜底
  - `OllamaProvider` `/api/generate` 封装 + health_check
  - `OpenAIProvider` Chat Completions 接口（云端切换即用）

- **SQLite 抽取主存** (`eqkg-poc/persist.py`)
  - 三表：documents（文档元数据）/ extract_runs（抽取运行）/ triples（三元组快照）
  - WAL 模式 + 外键级联 + dry_run 删除：`delete_document(doc_id, dry_run=True)`
  - Flask `/api/upload` 内存暂存 → SQLite 持久化
  - 新增端点：`GET /api/documents` 列表、`DELETE /api/documents/<id>` 删除

- **OCR 启用，6/6 装备全导入**
  - Tesseract 5.4.0（`C:\Program Files\Tesseract-OCR\`）复用已装版本
  - chi_sim 语言包放项目本地 `eqkg-poc/tessdata/`（Program Files 无写权限）
  - Flask `/api/upload` PDF 路径自动走 `smart_parse_pdf()`
  - 6 台装备：2 台文字层 + 4 台 OCR，共 87 三元组
  - OCR 速度：~3.5s/页（200dpi，纯 CPU）

### 改进

- qa_engine.py Neo4j/Ollama 连接从 config 读取，引用 ontology 白名单做安全校验
- qa-flask-app.py 上传路由：硬编码 PyMuPDF → Parser 策略层 + smart_parse_pdf
- .gitignore 加 `*.db` `*.db-*` `llm-graph-builder/`

### 修复

- parsers/__init__.py 未 import 实现文件导致注册表为空（装饰器不触发）
- ocr_parser.py `--tessdata-dir "path"` 引号被当路径一部分 → 改用 `TESSDATA_PREFIX` 环境变量

### 依赖

- 新增：pytesseract, pillow, python-docx, pydantic-settings（可选）

---

## [v0.1.0] — 2026-10-16

### 新增

- **规则抽取 PoC** (`eqkg-poc/eqkg_extractor.py`)
  - COMPONENT_PATTERNS / ATTR_PATTERNS / FAULT_WORDS / REPAIR_WORDS 四组正则
  - `extract_from_text(text, equipment_name)` → list[triple]
  - `extract_from_pdf(path)` → dict(equipment, triples, text_len, is_scanned)
  - `merge_triples(driver, triples)` Neo4j MERGE 去重写入
  - `detect_equipment_name(text, filename)` 正则识别型号，退化到文件名清理

- **Flask 问答 Web UI** (`eqkg-poc/qa-flask-app.py`)
  - 单文件嵌入 HTML，三 Tab：❓ 问答 / 📥 文档导入 / 📊 图谱预览
  - `/api/upload` → `/api/commit` 两段式导入（预览→确认 MERGE）

- **问答引擎** (`eqkg-poc/qa_engine.py`)
  - RULE_TEMPLATES 5 组规则模板，瞬间命中
  - `run_cypher()` 安全只读执行（禁写 + 强制 LIMIT）
  - `llm_text2cypher()` Ollama Text2Cypher 兜底（CPU 下较慢，默认关）

- **Neo4j Docker 容器**（WSL2）
  - Neo4j 5.23+ + APOC 5.26.32 + GDS 2.13.14
  - bolt://localhost:7687 / neo4j / eqkg2026

- **初始图谱数据**
  - 2 台测序仪（文字层可读），70 节点 / 70 关系
  - 4 台扫描件（POCT/酶标仪/扫描电镜/荧光计）：0 文字层

### 已知问题

- qwen3.5:4b thinking 能力在 CPU 下烧 ~188 隐藏思维 token，每个请求 87s → 切换 qwen2.5:7b
- qwen2.5:7b 纯 CPU 下抽取 6 页 PDF 需 200-400s，Ollama 模型切换反复卸载
- GitHub 完全封（HTTPS 000）→ 改用 SSH 22 端口 + pypi 清华镜像

---

## 版本规划

| 版本 | 目标 | 状态 |
|------|------|------|
| v0.1.0 | 规则抽取 PoC + Flask UI + 2 台装备图谱 | ✅ 完成 |
| v0.2.0 | 架构升级（ontology/config/parsers/providers/persist）+ OCR 启用 | ✅ 完成 |
| v0.3.0 | 故障质量修复 + 装备型号标准化 + 图谱问答增强 | 📋 规划中 |
| v1.0.0 | 本体工程 + LLM 抽取（需 GPU）+ 前端 React 重写 | 📋 远景 |
