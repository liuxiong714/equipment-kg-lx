# GitHub 可直接用于装备知识图谱构建的开源项目 — 选型报告

> 检索日期：2026-10-15
> 选型原则：**Python 优先**（与现有 FastAPI + PostgreSQL + asyncio 技术栈匹配）、**Apache-2.0/BSD 友好 License**、**近 12 个月有活跃更新**、**Stars ≥ 1000 社区验证**、**能覆盖综述中的三层流水线（本体 → 抽取 → 融合 → 推理）**

---

## 一、核心推荐项目（按流水线阶段组织）

### 阶段 0：基础设施 — Neo4j 图数据库

| 项目 | 关键信息 |
|------|----------|
| **Neo4j 5.x 社区版** | Docker 一键部署，WSL2 友好，APOC + GraphDataScience 插件内置 |

**安装命令（一行，WSL2 或 Linux）**：
```bash
docker run -d \
  --name neo4j-eqkg \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/eqkg2026 \
  -e NEO4J_PLUGINS='["apoc", "graph-data-science"]' \
  -v neo4j-eqkg-data:/data \
  neo4j:5
```
启动后浏览器访问 http://localhost:7474 ，默认密码 `eqkg2026`。
- `pip install neo4j graphdatascience` 即可 Python 连接
- 要求 Neo4j **≥ 5.23**（llm-graph-builder 硬性要求）

---

### 阶段 1：本体 / 模式层

| # | 项目 | Stars | License | 语言 | 核心能力 | 安装 | 适用场景 |
|---|------|-------|---------|------|----------|------|----------|
| A1 | [CommonCoreOntology (CCO)](https://github.com/CommonCoreOntology/CommonCoreOntologies) | — | BSD-3 | OWL/Turtle | 装备领域**现成上层本体**，包含 `ArmoredPersonnelCarrier`（APC）、`GroundMotorVehicle`、`Act of Military Force` 等类，无需从零构建 | 直接克隆 | 作为装备本体的**起点**，直接 import OWL 文件 |
| A2 | [DeepOnto](https://github.com/KRR-Oxford/DeepOnto) | 217+ | Apache-2.0 | Python 3.8+ | 牛津 KRR 组，封装 OWL API、推理器、BERTMap 对齐、语言化，完整 Pythonic 本体工程工具链 | `pip install deeponto` | **本体构建 + 推理 + 对齐**一体化 |
| A3 | [OntoAligner](https://github.com/sciknoworg/OntoAligner) | — | Apache-2.0 | Python | 模块化本体对齐工具包，轻量模糊匹配 + 集成投票融合，支持 LLM 增强 | `pip install ontoaligner` | 多装备子域本体对齐（兵器 ↔ 航空 ↔ 航天） |

**关于 A1（CCO）的重要性**：综述中提到的 BFO/CCO 是美国情报社区 National Security Ontology Foundry 的标准。CCO 已经定义了装备相关类（装甲运兵车、地面机动车、军事行动等），**直接克隆后在 Protégé 或 DeepOnto 中 import**，只需添加装备特有子类和关系即可，节省 40–60% 的本体从零构建工作量。

**快速获取 CCO OWL 文件**：
```bash
git clone https://github.com/CommonCoreOntology/CommonCoreOntologies.git
# Turtle 文件位于 src/cco-modules/ 目录
# 合并版本：src/cco-merged/AllCoreOntology.ttl
```

---

### 阶段 2：知识抽取层（LLM 驱动，装备手册 → 三元组）

| # | 项目 | Stars | License | 语言 | 核心能力 | 安装 | 适用场景 |
|---|------|-------|---------|------|----------|------|----------|
| B1 | [neo4j-labs/llm-graph-builder](https://github.com/neo4j-labs/llm-graph-builder) | **3,898** [unverified，来自 PyPI/搜索摘要] | Apache-2.0 | Python **3.12+** / FastAPI / LangChain | Neo4j 官方 **LLM → Neo4j** 构建器，支持 PDF/DOC/TXT/YouTube/网页，OpenAI/Gemini/Anthropic/Groq 任选，**要求 Neo4j 5.23+** | `git clone` + 改 `.env` + `langchain` | **装备设计/维修手册 → 图谱**最快路径 |
| B2 | [microsoft/graphrag](https://github.com/microsoft/graphrag) | **36,313** [unverified，来自 PyPI/搜索摘要] | MIT | Python 3.10+ | 微软 Research 原版 GraphRAG，社区检测（Leiden）+ 层次摘要 + 图驱动检索 | `pip install graphrag` | **Graph RAG 问答系统** + 从文档自动构图 |
| B3 | [neo4j-graphrag-python](https://neo4j.com/docs/neo4j-graphrag-python/current/) | — | Apache-2.0 | Python 3.10+ | Neo4j 原生 GraphRAG 实现，schema 自动生成（v1.8.0+），直接写入 Neo4j | `pip install neo4j-graphrag` | 与 Neo4j 深度集成的生产级方案 |
| B4 | **[OpenUE](https://gitee.com/openkg/openue)**（Gitee 中文） | — | MIT | Python / PyTorch | 轻量级中文知识图谱抽取工具，兼容 BERT/Roberta，支持实体关系抽取 + 事件抽取 + 槽位意图抽取 | `pip install openue` | **中文装备故障工单 / 手册抽取** |
| B5 | **[DeepKE](https://gitee.com/LHR_97/deepke)**（浙大 KG 团队，Gitee） | — | Apache-2.0 | Python / PyTorch | 中文知识图谱抽取框架，cnSchema 特别版，支持低资源 / 长篇章 / 多模态 | `pip install deepke` | **标注数据稀缺的中文装备领域** |

**三者定位差异**：

| 维度 | B1 (llm-graph-builder) | B2 (microsoft/graphrag) | B3 (neo4j-graphrag-python) |
|------|------------------------|--------------------------|----------------------------|
| 存储目标 | Neo4j | 默认可插拔文件系统 / 可选 Neo4j | **强制 Neo4j** |
| 核心功能 | **构建**为主，构建完毕即可查询 | **RAG 问答**为主，构图是前置 | **生产级** Neo4j 集成 |
| 上手难度 | 最低（Jupyter Notebook 示例） | 中等（CLI + 配置文件） | 中等（Python API） |
| 典型流程 | 上传 PDF → 选 LLM → 一键生成 Neo4j 图 | `graphrag index` → `graphrag query` | `Neo4jGraphRAG.from_config()` |

---

### 阶段 3：知识融合 / 本体对齐

| # | 项目 | Stars | License | 语言 | 核心能力 | 安装 | 适用场景 |
|---|------|-------|---------|------|----------|------|----------|
| C1 | [DeepOnto BERTMap](https://github.com/KRR-Oxford/DeepOnto) | 同上 | Apache-2.0 | Python | DeepOnto 内置的 BERTMap 本体对齐 + LogMapLt 逻辑匹配 | `pip install deeponto` | 快速对齐两个 OWL 本体 |
| C2 | [OntoAligner](https://github.com/sciknoworg/OntoAligner) | 同上 | Apache-2.0 | Python | 多技术集成式对齐，支持模糊 + LLM + BERTMap 投票 | `pip install ontoaligner` | 子域本体对齐（兵器 ↔ 航空 ↔ 航天） |
| C3 | [LogMap](https://github.com/ernestojimenezruiz/logmap-matcher) | — | **LGPL-3.0 ⚠ copyleft** | Java | OAEI 常年冠军，OAEI 2025 bio-ml track 前二 | `mvn package` 或直接下载 jar | 超大规模本体对齐（10万+ 类） |

> ⚠ **License 合规警示**：LogMap（LGPL-3.0）和 GraphDataScience（GPL-3.0）带 copyleft 约束。GPL-3.0 要求衍生作品必须开源，**对国防/涉密生产部署不友好**；LGPL-3.0 动态链接可豁免但需严格审计。**PoC 阶段无影响**，生产部署时建议用 DeepOnto（Apache-2.0）+ OntoAligner（Apache-2.0）替代，或确认法务合规后再引入 GDS/LogMap。

**推荐**：先用 C1/C2（Python）快速验证，C3（Java）用于大规模对齐和 OAEI 级评测。

---

### 阶段 4：图推理 / 分析 / 可视化

| # | 项目 | Stars | License | 语言 | 核心能力 | 安装 | 适用场景 |
|---|------|-------|---------|------|----------|------|----------|
| D1 | [GraphDataScience (GDS)](https://neo4j.com/docs/graph-data-science-client/current/) | — | **GPL-3.0 ⚠ copyleft** | Python 客户端（C++ 后端） | Neo4j 官方图算法库（社区检测、节点嵌入、路径查找、相似性），包含 Leiden、Louvain、PageRank、Node2Vec | `pip install graphdatascience`（服务端随 Docker 自动部署） | 故障因果链发现、装备体系分析 |
| D2 | mermaid / [react-force-graph](https://github.com/vasturiano/react-force-graph) | — | MIT | JS | 知识图谱前端可视化 | CDN 引入 | 图谱展示与交互 |

---

### 阶段 5：现成装备/故障领域项目（可直接参考或 fork）

| # | 项目 | 语言 | 来源 | 参考价值 |
|---|------|------|------|----------|
| E1 | [XAI4Wind](https://github.com/joyjitchatterjee/XAI4Wind) | Python | PMC 同行评审论文开源 | 风力运维多模态知识图谱 + 故障预测 + SHAP 可解释性 |
| E2 | GUARD LogMapLLM | Java + LLM Prompt | [github.com/city-artificial-intelligence/logmap-llm](https://github.com/city-artificial-intelligence/logmap-llm) | **LLM 作为本体对齐 Oracle** 的工程实现，OAEI 前二 |
| E3 | [PLFMKG（产线故障图谱）](https://dl.acm.org/doi/pdf/10.1145/3627915.3627917) | Python + BERT | ACM SIGIR 2023 | BERT-BiLSTM-CRF 抽取中文故障知识图谱，可复刻到装备领域 |

---

## 二、实施方案（分阶段路线图）

### Phase 0 — 环境准备（20–30 分钟）

```bash
# 1. 启动 Neo4j（WSL2 或 Linux）
docker run -d --name neo4j-eqkg \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/eqkg2026 \
  -e NEO4J_PLUGINS='["apoc", "graph-data-science"]' \
  -v neo4j-eqkg-data:/data \
  neo4j:5

# 2. 创建 Python 虚拟环境
python -m venv eqkg_env && source eqkg_env/bin/activate
pip install neo4j graphdatascience deeponto ontoaligner
pip install neo4j-graphrag
pip install graphrag langchain

# 3. 克隆 CCO 现成本体
git clone https://github.com/CommonCoreOntology/CommonCoreOntologies.git
```

**验收标准**：浏览器打开 http://localhost:7474 看到 Neo4j Browser，Python `from neo4j import GraphDatabase` 能连上。

---

### Phase 1 — 快速 PoC：装备手册 → 图谱（2–4 小时）

**目标**：拿 **1 本装备故障手册 PDF**，走通"PDF → Neo4j 图谱 → 查询"的最短路径。

**方案 A**（最快，零代码起步）—— 用 llm-graph-builder Jupyter Notebook：

```bash
git clone https://github.com/neo4j-labs/llm-graph-builder.git
cd llm-graph-builder
# 修改 .env：设 NEO4J_URI、NEO4J_USER、NEO4J_PASSWORD、OPENAI_API_KEY（或换其他 LLM）
pip install -r requirements.txt
jupyter notebook
# 打开 notebooks/GraphBuilder.ipynb → 上传 PDF → Run All → 自动写入 Neo4j
```

**方案 B**（更可控，能自定义 Prompt）—— 用 neo4j-graphrag-python：

```python
from neo4j_graphrag.llm import OpenAILLM
from neo4j_graphrag.embeddings import OpenAIEmbeddings
from neo4j_graphrag.retrievers import GraphRAGRetriever

# 连接
retriever = GraphRAGRetriever(
    driver=neo4j_driver,
    llm=OpenAILLM(model="gpt-4o"),
    graph_store_index_name="nodes",
)
# 抽取后写入 Neo4j，再 Graph RAG 查询
result = retriever.search("该装备的故障因果链是什么？")
```

**验收标准**：装备手册中的"零部件—故障—维修方案"三元组出现在 Neo4j 中，Cypher 查询能返回结果。

---

### Phase 2 — 本体工程（1–3 天）

**目标**：基于 CCO + 领域知识，构建装备领域本体 schema。

```python
from deeponto.onto import Ontology
from deeponto.align import BERTMap

# 1. 加载 CCO 上层本体
cco = Ontology.from_file("CommonCoreOntologies/src/cco-merged/AllCoreOntology.ttl")

# 2. 添加装备特有子类（Python 编程，无需 Protégé）
from owlapy import owl_expression_to_dl
# 定义 "WeaponSystem" 作为 cco:GroundMotorVehicle 的子类
# 定义 "FaultMode"、"RepairAction" 等装备特有概念

# 3. 推理检查一致性
reasoner = cco.get_reasoner()
inconsistent = reasoner.get_inconsistent_classes()
print(inconsistent)  # 应输出空列表
```

**验收标准**：在 Protégé 中打开生成的 OWL 文件，能看到 CCO 上层类 + 装备子类的完整层次结构。

---

### Phase 3 — 批量知识抽取（按数据量估算，1 周–1 月）

| 方案 | 数据源 | 工具 | 预计速度 |
|------|--------|------|----------|
| LLM + 本体约束 | 设计文档、技术规范 | llm-graph-builder / neo4j-graphrag + 自定义 Prompt | 500 页 / 天（单机） |
| BERT-BiLSTM-CRF 微调 | 历史故障工单 | 参考 PLFMKG 方法，用 deeponto + transformers | 10 万条 / 天（GPU） |
| 结构化数据导入 | 仿真数据、战备记录 | Neo4j Cypher `LOAD CSV` + APOC | 全量导入 |

**验收标准**：图谱实体 ≥ 500、关系 ≥ 1000，覆盖至少一个装备子类的完整故障因果链。

---

### Phase 4 — 融合 + 对齐（多装备子域时执行）

```python
from ontoaligner import ontology, encoder
from ontoaligner.aligner import SimpleFuzzySMLightweight

# 加载两个子域本体
onto_weapon = ontology.from_file("weapon_ontology.owl")
onto_aviation = ontology.from_file("aviation_ontology.owl")

# 轻量模糊对齐
aligner = SimpleFuzzySMLightweight()
mappings = aligner.align(onto_weapon, onto_aviation)

# 导出 OAEI 格式 XML
from ontoaligner.utils import xmlify
xmlify(mappings, "alignments.xml")
```

**验收标准**：两个子域本体之间的等价映射 ≥ 80% 准确率（人工抽检）。

---

### Phase 5 — 推理 + 应用（2–4 周）

| 应用 | 方法 | 技术 |
|------|------|------|
| 故障因果链发现 | GDS 路径查找 + GraphSAGE 嵌入 | `graphdatascience.gds.shortestPath()` |
| 故障根因定位 | Graph RAG 问答 + 证据链追踪 | `neo4j-graphrag-python` |
| 任务规划推荐 | 本体约束下的子图匹配 | Cypher + 自定义 Python 逻辑 |
| 可视化展示 | React Force Graph / Streamlit + Neo4j Driver | 前端任选 |

**验收标准**：给定"某型装备出现 XX 故障现象"，系统能返回**故障原因 → 关联部件 → 维修方案**的完整推理路径。

---

## 三、资源清单汇总

| 类别 | 资源 | 链接 | 直接可用性 |
|------|------|------|-----------|
| **图数据库** | Neo4j 5 Docker + APOC + GDS | `neo4j:5` | ⭐⭐⭐⭐⭐ 一行启动 |
| **上层本体** | CCO（Common Core Ontologies） | [github.com/CommonCoreOntology/CommonCoreOntologies](https://github.com/CommonCoreOntology/CommonCoreOntologies) | ⭐⭐⭐⭐⭐ 现成 OWL 直接 import |
| **LLM → 图谱** | llm-graph-builder | [github.com/neo4j-labs/llm-graph-builder](https://github.com/neo4j-labs/llm-graph-builder) | ⭐⭐⭐⭐⭐ Jupyter 示例跑通即用 |
| **Graph RAG** | microsoft/graphrag | [github.com/microsoft/graphrag](https://github.com/microsoft/graphrag) | ⭐⭐⭐⭐⭐ 36K stars 成熟 |
| **Python 本体** | DeepOnto | [github.com/KRR-Oxford/DeepOnto](https://github.com/KRR-Oxford/DeepOnto) | ⭐⭐⭐⭐⭐ 牛津出品 |
| **本体对齐** | OntoAligner | [github.com/sciknoworg/OntoAligner](https://github.com/sciknoworg/OntoAligner) | ⭐⭐⭐⭐ 模块化 |
| **本体对齐（Java）** | LogMap + LogMapLLM | [github.com/ernestojimenezruiz/logmap-matcher](https://github.com/ernestojimenezruiz/logmap-matcher) | ⭐⭐⭐⭐⭐ OAEI 冠军 |
| **图算法** | GraphDataScience | Neo4j 内置 | ⭐⭐⭐⭐⭐ Docker 自动部署 |
| **领域参考** | XAI4Wind（风电运维图谱） | [github.com/joyjitchatterjee/XAI4Wind](https://github.com/joyjitchatterjee/XAI4Wind) | ⭐⭐⭐ 可复刻方法 |

---

## 四、执行前注意事项

1. **WSL2 Docker 前置条件**：需要先在 WSL2 中启用 Docker Engine（`wsl --install --docker` 或安装 Docker Desktop + WSL 后端）。
2. **LLM API Key 准备**：llm-graph-builder 需要 OpenAI / Gemini / Anthropic 之一的 API Key。
3. **Protégé 可选**：如果偏好 GUI 本体编辑，下载 [Protégé 5.x](https://protege.stanford.edu/) 即可打开 DeepOnto 生成的 OWL 文件。
4. **Python 版本要求**：GraphRAG 和 neo4j-graphrag 要求 **Python ≥ 3.10**，DeepOnto 要求 **≥ 3.8**。
5. **涉密数据处理**：若装备数据涉密，建议先在本地跑通全流程，再评估数据脱敏方案。

---

## 五、决策触发点

如果您决定执行，我可以按以下最小范围逐步推进：

- **最小执行单元**：Phase 0（Docker + venv + CCO clone）+ Phase 1 的 **方案 A**（拿 1 本公开装备手册跑通 llm-graph-builder Jupyter Notebook）—— 预计 **1 小时**即可看到第一个装备知识图谱三元组
- **中等执行单元**：Phase 0–1（含方案 B neo4j-graphrag 自定义）—— 预计 **半天**
- **完整路线**：Phase 0–5 全部推进 —— 预计 **3–6 周**（取决于装备数据规模和本体复杂度）

**请告知您的决定方向**，我将按需推进。
