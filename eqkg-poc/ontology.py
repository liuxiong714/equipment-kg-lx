"""装备知识图谱本体定义。

实体类型（EntityType）与关系类型（RelationType）用于描述
装备说明书/手册抽取的语义网络。

来源：
1. 规则抽取：eqkg_extractor.py 正则抽取 + MERGE 入 Neo4j
2. LLM 抽取：将来 GPU 就绪后由 LLM 按同一本体输出 JSON
"""

from enum import Enum


class EntityType(str, Enum):
    # === 核心实体 ===
    EQUIPMENT = "Equipment"          # 装备主体（测序仪、分析仪、电镜...）
    COMPONENT = "Component"          # 部件（触摸屏、电源模块、电机...）
    FAULT = "Fault"                  # 故障模式（温度异常、无法识别试剂...）
    FUNCTION = "Function"            # 功能（单Barcode测序、温控、高通量...）
    ATTRIBUTE = "Attribute"          # 参数属性（型号、电压、重量、通量...）
    SOLUTION = "Solution"            # 维修/校准/更换方案

    # === 扩展实体 ===
    SENSOR = "Sensor"                # 传感器（光电、温度、压力...）
    REAGENT = "Reagent"              # 试剂（测序试剂、反应液、缓冲液...）
    MANUFACTURER = "Manufacturer"    # 厂家（华大智造、Thermo Fisher...）
    DOCUMENT = "Document"            # 文档来源（产品说明书、彩页、操作手册...）


class RelationType(str, Enum):
    # === 装备维度 ===
    HAS_COMPONENT = "HAS_COMPONENT"               # 装备 → 部件
    HAS_ATTRIBUTE = "HAS_ATTRIBUTE"               # 装备 → 参数属性
    PERFORMS_FUNCTION = "PERFORMS_FUNCTION"       # 装备 → 功能
    HAS_FAULT_MODE = "HAS_FAULT_MODE"             # 装备 → 故障模式
    USES_REAGENT = "USES_REAGENT"                 # 装备 → 试剂
    HAS_SENSOR = "HAS_SENSOR"                     # 装备/部件 → 传感器
    MANUFACTURED_BY = "MANUFACTURED_BY"           # 装备 → 厂家

    # === 故障维度 ===
    REPAIRED_BY = "REPAIRED_BY"                   # 故障 → 维修方案
    CAUSES = "CAUSES"                             # 故障 → 故障（级联）
    LOCATED_IN = "LOCATED_IN"                     # 故障 → 部件（故障发生部位）

    # === 功能维度 ===
    REQUIRES_COMPONENT = "REQUIRES_COMPONENT"     # 功能 → 所需部件

    # === 层次 ===
    IS_A = "IS_A"                                 # 实体 → 上位类（传感器 IS_A 部件）
    PART_OF = "PART_OF"                           # 部件 → 子部件

    # === 溯源 ===
    DESCRIBED_IN = "DESCRIBED_IN"                 # 实体/关系 → 文档


# 实体中文标签（前端/日志用）
ENTITY_LABELS: dict[EntityType, str] = {
    EntityType.EQUIPMENT: "装备",
    EntityType.COMPONENT: "部件",
    EntityType.FAULT: "故障",
    EntityType.FUNCTION: "功能",
    EntityType.ATTRIBUTE: "参数",
    EntityType.SOLUTION: "维修方案",
    EntityType.SENSOR: "传感器",
    EntityType.REAGENT: "试剂",
    EntityType.MANUFACTURER: "厂家",
    EntityType.DOCUMENT: "文档",
}

# 关系中文标签
RELATION_LABELS: dict[RelationType, str] = {
    RelationType.HAS_COMPONENT: "包含部件",
    RelationType.HAS_ATTRIBUTE: "具有参数",
    RelationType.PERFORMS_FUNCTION: "具备功能",
    RelationType.HAS_FAULT_MODE: "故障模式",
    RelationType.USES_REAGENT: "使用试剂",
    RelationType.HAS_SENSOR: "配备传感器",
    RelationType.MANUFACTURED_BY: "由...制造",
    RelationType.REPAIRED_BY: "维修方案",
    RelationType.CAUSES: "导致",
    RelationType.LOCATED_IN: "发生在",
    RelationType.REQUIRES_COMPONENT: "依赖部件",
    RelationType.IS_A: "是一种",
    RelationType.PART_OF: "属于...的一部分",
    RelationType.DESCRIBED_IN: "来源于",
}


# Neo4j 写入时允许的关系名白名单（安全校验用）
ALLOWED_RELATIONS: set[str] = {r.value for r in RelationType}

# Neo4j 写入时允许的实体标签白名单
ALLOWED_LABELS: set[str] = {e.value for e in EntityType}
