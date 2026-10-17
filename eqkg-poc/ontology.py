"""装备知识图谱本体定义（权威版本）。

来源：用户提供的《本体层.xlsx》（56 概念类 + 20 关系 + 36 属性）
     + 《三元组表与节点属性表.xlsx》（实际抽取发现 65 个长尾属性）

三层结构:
  1. ENTITY_TYPES — 56 个概念类，带层级树（parent-child）
  2. RELATION_TYPES — 20 个关系，每个带 domain→range 约束
  3. ATTRIBUTE_KEYS — 101 个属性（36 标准 + 65 长尾），绑定所属概念类

核心函数:
  validate_triple(head_code, rel_code, tail_code) → bool
  —— MERGE 进 Neo4j 前强制校验 (domain, type, range) 三元组约束

用法:
  from ontology import ENTITY_TYPES, RELATION_TYPES, ATTRIBUTE_KEYS, validate_triple
  validate_triple("E01-01", "adopts", "E03-01")  # True
  validate_triple("E01-01", "adopts", "E07-01")  # False (range 不匹配)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ============================================================
# 实体概念类
# ============================================================
@dataclass(frozen=True)
class EntityDef:
    """本体概念类定义。"""
    code: str                 # E01-01
    name_zh: str              # 生物侦检装备
    level: str                # 根节点 / 一级 / 二级
    parent: Optional[str]     # 上位本体的 code（E01 或 None 表示根）
    definition: str = ""
    examples: str = ""

    @property
    def neo4j_label(self) -> str:
        """Neo4j 节点用此 label（下划线替代连字符，避免特殊字符问题）。"""
        return self.code.replace("-", "_")


# ---------- 56 个概念类 ----------
# 结构: code, name_zh, level, parent, definition, examples
_RAW_ENTITIES = [
    # E00 根
    ("E00", "装备", "根节点", None,
     "野战条件下遂行卫生防疫与疫情防控任务的装备、器材、药剂及其配套人员、组织、任务、场所、疾病病媒、能力与法规知识的总称",
     ""),
    # E01 装备类型（8 个二级）
    ("E01", "装备类型", "一级", "E00",
     "野战防疫队遂行防疫任务使用的各类装备、器材、车辆与方舱的总称", ""),
    ("E01-01", "生物侦检装备", "二级", "E01",
     "用于发现、报警、识别生物战剂与病原体的侦察与检测装备",
     "生物气溶胶报警装备、生物战剂与病原体检验装备"),
    ("E01-02", "消毒灭菌装备", "二级", "E01",
     "对环境、物体表面、器材、人员进行消毒灭菌的装备",
     "车载消杀装备、空间与物体表面消毒装备、灭菌器械"),
    ("E01-03", "个体防护装备", "二级", "E01",
     "保护人员免受生物、化学、物理伤害的个体防护器材",
     "呼吸防护装备、躯体防护装备、卫生装备"),
    ("E01-04", "检验检测与采样装备", "二级", "E01",
     "用于环境、空气、样本检验检测及现场采样的装备",
     "环境与空气检测装备、现场采样装备"),
    ("E01-05", "医疗救护与预防用药装备", "二级", "E01",
     "用于急救、医疗救治、预防接种与疫苗药品储运的装备",
     "急救箱、呼吸机、接种装备、疫苗药品储运装备"),
    ("E01-06", "通信指挥与信息装备", "二级", "E01",
     "用于通信联络、信息处理与指挥调度的装备",
     "通信装备、信息处理与办公装备、音视频采集与传输设备"),
    ("E01-07", "运输投送与携行装备", "二级", "E01",
     "用于标本、人员、装备运输投送及携行的装备",
     "标本保存与转运装备、生防急救车/救护车、无人机"),
    ("E01-08", "后勤保障与环境卫生装备", "二级", "E01",
     "用于帐篷搭建、卫生设施、废弃物处理等后勤保障的装备",
     "帐篷与工作场所、卫生设施、废弃物处理装备"),

    # E02 装备系统与部件
    ("E02", "装备系统与部件", "一级", "E00",
     "装备的系统结构、部件组成与型号标识", ""),
    ("E02-02", "配套装备", "二级", "E02",
     "与主装备配套使用的辅助装备", ""),
    ("E02-03", "装备部件", "二级", "E02",
     "构成装备的基本单元（主机、模块、传感器等）", ""),
    ("E02-04", "装备型号", "二级", "E02",
     "装备的具体型号标识", ""),

    # E03 装备原理与技术
    ("E03", "装备原理与技术", "一级", "E00",
     "装备的工作原理、采用技术与性能指标", ""),
    ("E03-01", "装备原理", "二级", "E03",
     "装备实现功能所采用的技术原理", ""),
    ("E03-02", "技术指标", "二级", "E03",
     "装备的量化技术参数",
     "消杀效能指标、检测效能指标、防护效能指标"),

    # E04 装备管理与保障
    ("E04", "装备管理与保障", "一级", "E00",
     "装备的全寿命周期管理：配备、维护、维修", ""),
    ("E04-01", "装备管理", "二级", "E04",
     "装备的配备、编配、采购、验收、保管与使用",
     "配备与编配标准、采购与验收"),
    ("E04-02", "装备维护", "二级", "E04",
     "装备的日常保养、状态监测与试剂耗材效期管理",
     "日常保养、试剂耗材效期管理、状态监测"),
    ("E04-03", "装备维修", "二级", "E04",
     "装备故障后的修理与恢复",
     "故障维修"),

    # E05 装备操作与运用
    ("E05", "装备操作与运用", "一级", "E00",
     "装备的操作规程、展开配置与使用要求", ""),
    ("E05-01", "操作使用", "二级", "E05",
     "装备的操作规程、条件与人员要求",
     "操作规程、操作条件与环境要求、操作人员资质"),
    ("E05-02", "展开与配置", "二级", "E05",
     "装备的场地选择、功能分区、展开时限与流程",
     "场地选择与功能分区、展开时限与流程"),

    # E06 生物防护与三防要素
    ("E06", "生物防护与三防要素", "一级", "E00",
     "防护等级、污染区划分与消毒处置方式", ""),
    ("E06-01", "防护等级", "二级", "E06",
     "生物安全防护等级",
     "A级（气密性全封闭）、B级、C级、D级"),
    ("E06-02", "污染区划分", "二级", "E06",
     "污染程度不同的功能区域划分",
     "清洁区、半污染区（缓冲/更衣区）、污染区、疫点与疫区"),
    ("E06-03", "消毒处置方式", "二级", "E06",
     "不同时机与目的的消毒处置方式",
     "预防性消毒、随时消毒、终末消毒"),

    # E07 防疫任务与场景
    ("E07", "防疫任务与场景", "一级", "E00",
     "防疫任务类型、运用场景与疫情事件", ""),
    ("E07-01", "防疫任务", "二级", "E07",
     "防疫作业的具体任务类型",
     "消毒作业、检测与检验任务、预防与干预任务、卫生监督任务"),
    ("E07-02", "运用场景", "二级", "E07",
     "装备与任务的应用场景",
     "抢险救灾卫生防疫、重大活动与口岸防疫保障"),
    ("E07-03", "疫情与公共卫生事件", "二级", "E07",
     "传染病暴发、群体性不明原因疾病等突发公共卫生事件",
     "传染病暴发疫情、群体性不明原因疾病、食物中毒事件"),

    # E08 防疫人员与组织单位
    ("E08", "防疫人员与组织单位", "一级", "E00",
     "防疫作业的人员与组织机构", ""),
    ("E08-01", "防疫人员", "二级", "E08",
     "从事防疫工作的专业人员",
     "流行病学调查员、专业技术人员、防疫作业人员"),
    ("E08-02", "防疫组织单位", "二级", "E08",
     "负责防疫组织指挥与作业的机构",
     "疾病预防控制中心、野战防疫队"),

    # E09 场所与环境
    ("E09", "场所与环境", "一级", "E00",
     "装备部署与任务执行的场所环境", ""),
    ("E09-01", "疫情相关场所", "二级", "E09",
     "与疫情发生直接相关的场所", "疫区"),
    ("E09-02", "生活与公共服务场所", "二级", "E09",
     "人员集中的生活与公共服务设施",
     "集中安置点、学校、医疗救助点"),
    ("E09-03", "自然环境与条件", "二级", "E09",
     "气象、地形、水源、媒介生物生境等自然条件",
     "气候气象、地形水文、媒介生物生境、水源地"),
    ("E09-04", "地理区域", "二级", "E09",
     "地理区域划分",
     "国家与地区、任务地域与点位"),

    # E10 时间
    ("E10", "时间", "一级", "E00",
     "时间节点与时效要求", ""),
    ("E10-01", "时间节点", "二级", "E10",
     "具体的时间点或时间段", ""),
    ("E10-02", "时效要求", "二级", "E10",
     "任务完成的时间限制", ""),

    # E11 疾病与病媒生物
    ("E11", "疾病与病媒生物", "一级", "E00",
     "传染病、病原微生物与媒介生物", ""),
    ("E11-01", "传染病", "二级", "E11",
     "由病原微生物引起的可传播疾病",
     "霍乱、鼠疫、炭疽、甲型肝炎"),
    ("E11-02", "病原微生物", "二级", "E11",
     "引起传染病的病原体",
     "霍乱弧菌、志贺菌、登革病毒"),
    ("E11-03", "媒介生物", "二级", "E11",
     "能够传播病原体的节肢动物和其他动物",
     "鼠、蚤、蜱、螨、蚊"),

    # E12 药剂与耗材
    ("E12", "药剂与耗材", "一级", "E00",
     "检验试剂、预防用药与免疫制剂", ""),
    ("E12-01", "检验试剂与耗材", "二级", "E12",
     "用于检验检测的试剂与配套耗材",
     "PCR试剂盒、核酸检测试剂、胶体金快检试剂"),
    ("E12-02", "预防用药与免疫制剂", "二级", "E12",
     "用于疾病预防的药物和疫苗",
     "甲肝疫苗、破伤风疫苗"),

    # E13 装备能力
    ("E13", "装备能力", "一级", "E00",
     "装备具备的作业能力与性能指标", ""),
    ("E13-01", "作业能力", "二级", "E13",
     "装备能够完成的作业类型",
     "检测能力、消杀能力、防护能力、生信分析能力"),
    ("E13-02", "性能指标", "二级", "E13",
     "装备的具体性能参数",
     "消杀效能指标、检测效能指标、防护效能指标、触摸屏规格、操作温度"),

    # E14 法规与技术标准
    ("E14", "法规与技术标准", "一级", "E00",
     "装备与防疫工作依据的法规、标准与规范", ""),
    ("E14-01", "法规制度", "二级", "E14",
     "法律法规与规章制度",
     "传染病防治法、国境卫生检疫法、消毒管理办法"),
    ("E14-02", "技术标准", "二级", "E14",
     "国家标准、行业标准与技术规范",
     "卫生防疫防护常用标准、生物安全实验室建筑技术规范"),
]

ENTITY_TYPES: dict[str, EntityDef] = {
    code: EntityDef(code=code, name_zh=zh, level=lvl, parent=parent,
                    definition=desc, examples=ex)
    for code, zh, lvl, parent, desc, ex in _RAW_ENTITIES
}


# ---------- 层级树查询 ----------
def get_children(code: str) -> list[EntityDef]:
    """返回某概念类的直接下级。"""
    return [e for e in ENTITY_TYPES.values() if e.parent == code]

def get_descendants(code: str) -> list[EntityDef]:
    """递归返回所有后代概念类。"""
    result = []
    for child in get_children(code):
        result.append(child)
        result.extend(get_descendants(child.code))
    return result

def is_descendant(child_code: str, ancestor_code: str) -> bool:
    """child_code 是否是 ancestor_code 的后代（含自己）。"""
    if child_code == ancestor_code:
        return True
    e = ENTITY_TYPES.get(child_code)
    while e and e.parent:
        if e.parent == ancestor_code:
            return True
        e = ENTITY_TYPES.get(e.parent)
    return False

def get_neo4j_label_set(code: str) -> set[str]:
    """返回某实体在 Neo4j 中应该打的所有 label（自身 + 所有祖先）。"""
    labels = set()
    e = ENTITY_TYPES.get(code)
    while e:
        labels.add(e.neo4j_label)
        e = ENTITY_TYPES.get(e.parent) if e.parent else None
    return labels


# ============================================================
# 关系类型（20 个，每个带 domain→range 约束）
# ============================================================
@dataclass(frozen=True)
class RelationDef:
    """本体关系定义。"""
    code: str                 # R-003
    name_zh: str              # 采用
    name_en: str              # adopts (Neo4j 关系标识)
    category: str             # 分类与组织 / 构成与配套 / 属性与能力 / 运用与功能 / 管理与保障 / 时空 / 事件因果 / 来源法规
    domain: tuple[str, ...]   # 允许的头实体概念类 codes
    range: tuple[str, ...]    # 允许的尾实体概念类 codes
    description: str = ""
    example: str = ""

    def validate(self, head_code: str, tail_code: str) -> bool:
        """检查 (head, self, tail) 是否满足 domain→range 约束。"""
        head_ok = any(is_descendant(head_code, d) for d in self.domain)
        tail_ok = any(is_descendant(tail_code, r) for r in self.range)
        return head_ok and tail_ok


# ---------- 20 个关系（domain/range 按 Excel 定义，用一级类覆盖其所有二级子类）----------
# 注意：Excel 里 domain 写的是"装备类型"这种一级类名，实际匹配时应该覆盖其所有二级子类
_RAW_RELATIONS = [
    # code, name_zh, name_en, category, domain, range, description, example
    ("R-001", "包含", "hasPart", "分类与组织",
     ("E00",), ("E01", "E02", "E03", "E04", "E05", "E06", "E07", "E08", "E09", "E10", "E11", "E12", "E13", "E14"),
     "上位概念包含其下级概念，构成本体层次结构", "装备类型 包含 消毒灭菌装备"),

    ("R-002", "配套", "matchedWith", "构成与配套",
     ("E01", "E02"), ("E01", "E02", "E12"),
     "装备与配套器材、药剂的配套使用关系", "超低容量喷雾器 配套 含氯消毒剂"),

    ("R-003", "采用", "adopts", "属性与能力",
     ("E01",), ("E03",),
     "装备采用某项技术实现功能", "生物气溶胶报警器 采用 生物气溶胶检测技术"),

    ("R-004", "具有", "has", "属性与能力",
     ("E01",), ("E03", "E13", "E02"),
     "装备具有某项技术指标、能力或型号", "超低容量喷雾器 具有 雾化粒径指标"),

    ("R-005", "执行任务", "performsTask", "运用与功能",
     ("E01", "E08-02"), ("E07-01",),
     "装备或组织单位执行某项防疫任务", "检验检测保障装备 执行任务 检测与检验任务"),

    ("R-006", "使用", "uses", "运用与功能",
     ("E08", "E08-01"), ("E01",),
     "人员或组织单位使用装备完成任务", "消杀作业组 使用 超低容量喷雾器"),

    ("R-007", "适用于", "applicableTo", "运用与功能",
     ("E01",), ("E09",),
     "装备适用的场所环境", "热烟雾机 适用于 灾害现场"),

    ("R-008", "针对", "targets", "运用与功能",
     ("E01", "E12"), ("E11-02", "E11-03"),
     "装备或药剂针对的病原微生物/媒介生物", "消毒剂 针对病原体 细菌类"),

    ("R-009", "参与", "participatesIn", "运用与功能",
     ("E01", "E08", "E08-02"), ("E07-03",),
     "装备或组织单位参与某疫情事件", "野战防疫队 参与 传染病暴发疫情"),

    ("R-010", "配备", "equippedWith", "管理与保障",
     ("E08-02",), ("E01",),
     "组织单位配备的装备", "野战防疫队 配备 卫生防疫车"),

    ("R-011", "管理", "managedBy", "管理与保障",
     ("E08", "E08-02"), ("E01",),
     "组织单位或人员管理装备", "装备管理组 管理 卫生防疫车"),

    ("R-012", "部署于", "deployedAt", "时空",
     ("E01", "E08-02"), ("E09",),
     "装备或组织单位的部署场所", "野战防疫队 部署于 营区与部署场所"),

    ("R-013", "作业时间", "hasOperationTime", "时空",
     ("E01", "E07-01"), ("E10-01",),
     "装备或任务的作业时间", "消杀任务 作业时间 2026-08-30"),

    ("R-014", "发生于", "occurredAt", "时空",
     ("E07-03",), ("E09", "E10-01"),
     "疫情事件发生的地点或时间", "传染病暴发疫情 发生于 疫区"),

    ("R-015", "涉及", "involves", "事件与因果",
     ("E07-03",), ("E11-02", "E11-03"),
     "疫情事件涉及的病原体或媒介生物", "传染病暴发疫情 涉及病原体 霍乱弧菌"),

    ("R-016", "触发任务", "triggersTask", "事件与因果",
     ("E07-03",), ("E07-01",),
     "疫情事件触发的防疫任务", "灾害事件 触发任务 消杀灭任务"),

    ("R-017", "导致", "causes", "事件与因果",
     ("E11-02", "E11-03"), ("E11-01",),
     "病原微生物或媒介生物导致传染病", "蚊 导致 登革热"),

    ("R-018", "预防", "prevents", "事件与因果",
     ("E12-02", "E01-03"), ("E11-01",),
     "疫苗或防护装备预防传染病", "甲肝疫苗 预防 甲型肝炎"),

    ("R-019", "依据", "basedOn", "来源与法规",
     ("E07-01", "E01"), ("E14",),
     "任务或装备依据的法规标准", "防疫作业 依据 GB 19082-2009"),

    ("R-020", "适用于", "appliesTo", "来源与法规",
     ("E14",), ("E07", "E08"),
     "法规标准适用的对象", "传染病防治法 适用于 防疫任务"),
]

RELATION_TYPES: dict[str, RelationDef] = {
    code: RelationDef(code=code, name_zh=zh, name_en=en, category=cat,
                      domain=tuple(dom), range=tuple(rng), description=desc, example=ex)
    for code, zh, en, cat, dom, rng, desc, ex in _RAW_RELATIONS
}


# ---------- Neo4j 兼容性（旧代码用 ALLOWED_RELATIONS）----------
ALLOWED_RELATIONS: set[str] = {r.name_en for r in RELATION_TYPES.values()}
ALLOWED_LABELS: set[str] = {e.neo4j_label for e in ENTITY_TYPES.values()}

# 关系中文名 → 英文名（抽取器输出中文名时映射）
REL_ZH_TO_EN: dict[str, str] = {r.name_zh: r.name_en for r in RELATION_TYPES.values()}
# 关系英文名 → code（validate_triple 查找用）
REL_EN_TO_CODE: dict[str, str] = {r.name_en: r.code for r in RELATION_TYPES.values()}
# 实体 code → Neo4j label
ENTITY_CODE_TO_LABEL: dict[str, str] = {e.code: e.neo4j_label for e in ENTITY_TYPES.values()}


# ============================================================
# 属性键定义（101 个：36 标准 + 65 长尾）
# ============================================================
@dataclass(frozen=True)
class AttributeDef:
    """本体属性定义。"""
    code: str                 # AT-001
    name_zh: str              # 装备名称
    name_en: str              # equipmentName
    applicable_concepts: tuple[str, ...]   # 可用于哪些概念类（一级 code）
    data_type: str = "TEXT"   # STRING | INT | FLOAT | DATE | ENUM | TEXT
    unit: str = ""
    required: bool = False
    example: str = ""


# ---------- 36 个标准属性（来自 Excel 本体层 3-属性表）----------
_STANDARD_ATTRIBUTES = [
    ("AT-001", "装备名称", "equipmentName", ("E01",), "STRING", "-", True, "多功能卫生防疫车"),
    ("AT-002", "装备编号", "equipmentCode", ("E01",), "STRING", "-", True, "FEP-2026-001"),
    ("AT-003", "装备类别", "equipmentCategory", ("E01",), "ENUM", "-", True, "消毒灭菌装备"),
    ("AT-004", "研制单位", "developer", ("E01",), "STRING", "-", False, "南京汽车集团有限公司"),
    ("AT-005", "生产厂家", "manufacturer", ("E01",), "STRING", "-", False, "程力专用汽车股份有限公司"),
    ("AT-006", "列装时间", "commissioningDate", ("E01",), "DATE", "年/年月", False, "2015-06"),
    ("AT-007", "防护等级", "protectionLevel", ("E01-03",), "ENUM", "-", False, "B级"),
    ("AT-008", "雾滴粒径", "dropletSize", ("E01-02",), "FLOAT", "μm", False, "小于20（90%累积）"),
    ("AT-009", "喷雾量/流量", "flowRate", ("E01-02",), "FLOAT", "L/h", False, "30"),
    ("AT-010", "射程/雾化距离", "sprayRange", ("E01-02",), "FLOAT", "m", False, "30~50"),
    ("AT-011", "药液罐容量", "tankCapacity", ("E01-02",), "FLOAT", "L", False, "2400"),
    ("AT-012", "杀菌率", "sterilizationRate", ("E01-02",), "FLOAT", "%", False, "99.99"),
    ("AT-013", "处理能力/喷洒面积", "treatmentCapacity", ("E01-02",), "FLOAT", "m2/h", False, "4200（每车）"),
    ("AT-014", "过滤效率", "filtrationEfficiency", ("E01-03",), "FLOAT", "%", False, "95"),
    ("AT-015", "检测限", "detectionLimit", ("E01-04", "E12-01"), "STRING", "-", False, "10^2 CFU/mL"),
    ("AT-016", "检出时间", "detectionTime", ("E01-04",), "FLOAT", "min", False, "15"),
    ("AT-017", "检测靶标", "detectionTarget", ("E01-04", "E12-01"), "STRING", "-", False, "霍乱弧菌、流感病毒"),
    ("AT-018", "外形尺寸", "dimensions", ("E01",), "STRING", "mm", False, "5900×1880×2200"),
    ("AT-019", "整备质量", "weight", ("E01",), "FLOAT", "kg", False, "2800"),
    ("AT-020", "工作环境温度", "operatingTemperature", ("E01",), "STRING", "℃", False, "-20~46"),
    ("AT-021", "防雨密封等级", "ipRating", ("E01",), "STRING", "-", False, "IP65"),
    ("AT-022", "配置数量", "quantity", ("E01",), "INT", "件/套/台", True, "3"),
    ("AT-023", "配备标准数量", "standardQuantity", ("E04-01",), "STRING", "套", False, "每次10套"),
    ("AT-024", "单价", "unitPrice", ("E01",), "FLOAT", "元", False, "2050"),
    ("AT-025", "使用寿命", "serviceLife", ("E01",), "INT", "年", False, "10"),
    ("AT-026", "装备状态", "equipmentStatus", ("E01",), "ENUM", "-", True, "完好"),
    ("AT-027", "完好率", "readinessRate", ("E04-01",), "FLOAT", "%", False, "95"),
    ("AT-028", "检定校准周期", "calibrationCycle", ("E04-01",), "INT", "月", False, "12"),
    ("AT-029", "有效期", "shelfLife", ("E12",), "DATE", "-", False, "2026-12-31"),
    ("AT-030", "储存条件", "storageCondition", ("E12",), "STRING", "-", False, "2~8℃冷藏、避光"),
    ("AT-031", "展开时限", "deploymentTimeLimit", ("E05-02",), "FLOAT", "min", False, "30"),
    ("AT-032", "依据标准号", "standardNo", ("E14",), "STRING", "-", False, "GB 19082-2009"),
    ("AT-033", "适用范围", "applicableScope", ("E01",), "STRING", "-", False, "部队集结地、野战医院、居民点"),
    ("AT-034", "操作人员资质要求", "operatorRequirement", ("E05-01",), "STRING", "-", False, "经专业培训并考核合格"),
    ("AT-035", "功能描述", "functionDescription", ("E01",), "TEXT", "-", False, "喷洒液体与粉末状防疫药物，实施杀虫与消毒"),
    ("AT-036", "关键部件清单", "keyComponents", ("E02",), "TEXT", "-", False, "药仓、圆筒喷射器、柴油发电机组、喷雾装置"),
]

# ---------- 65 个长尾属性（来自实际抽取 Excel 三元组表）----------
_LONGTAIL_ATTRIBUTES = [
    # 测序仪专属
    ("AT-037", "触摸屏规格", "touchScreen", ("E01-01",), "STRING", "-", False, "触摸屏12.1英寸/1280×800像素"),
    ("AT-038", "操作相对湿度", "operatingHumidity", ("E01-01",), "STRING", "%", False, "相对湿度≤85%RH"),
    ("AT-039", "大气压力范围", "atmosphericPressure", ("E01-01",), "STRING", "kPa", False, "70~106"),
    ("AT-040", "污染等级", "pollutionDegree", ("E01-01",), "STRING", "-", False, "污染等级2级"),
    ("AT-041", "主机输入电源", "mainUnitPowerInput", ("E01-01",), "STRING", "-", False, "12V DC"),
    ("AT-042", "计算模块电源输入", "computerPowerInput", ("E01-01",), "STRING", "-", False, "12V DC"),
    ("AT-043", "运输/储存温度", "transportStorageTemp", ("E01-01",), "STRING", "℃", False, "-25~55"),
    ("AT-044", "最大声压级", "maxSoundPressure", ("E01-01",), "STRING", "dB", False, "<60"),
    ("AT-045", "软件配置", "softwareConfig", ("E01-01",), "STRING", "-", False, "DNBSEQ-E 测序软件"),
    ("AT-046", "占桌面积", "desktopArea", ("E01-01",), "STRING", "mm", False, "515×220"),
    ("AT-047", "单次运行数据量", "dataOutput", ("E01-01",), "STRING", "-", False, "最多400G字节/次"),
    ("AT-048", "单次运行Reads数", "readsPerRun", ("E01-01",), "INT", "M", False, "400M/次"),
    ("AT-049", "测序时间", "sequencingTime", ("E01-01",), "STRING", "s/M", False, "≤0.32s/M"),
    ("AT-050", "Q30值", "q30", ("E01-01",), "STRING", "%", False, "≥92%"),
    ("AT-051", "加载方式", "sampleLoadingMode", ("E01-01",), "STRING", "-", False, "手动加载"),
    ("AT-052", "样本通量", "sampleThroughput", ("E01-01",), "STRING", "samples/day", False, "192样本/天"),
    ("AT-053", "荧光通道数", "fluorescenceChannels", ("E01-01",), "INT", "-", False, "4色荧光通道"),
    ("AT-054", "荧光靶标检测能力", "targetCapability", ("E01-01",), "STRING", "-", False, "最高48重靶标检测"),
    ("AT-055", "电源要求", "powerRequirement", ("E01-01",), "STRING", "-", False, "主机180W / 计算模块50W"),
    ("AT-056", "乘员数", "crew", ("E01",), "INT", "人", False, "乘员数"),
    ("AT-057", "空气过滤能力", "airFiltrationCapacity", ("E01-01",), "STRING", "-", False, "HEPA H13"),
    # 酶标分析仪专属
    ("AT-058", "芯片样本通道数", "chipChannels", ("E01-04",), "INT", "通道", False, "4通道"),
    ("AT-059", "手工操作时间", "manualOperationTime", ("E01-04",), "STRING", "min", False, "<30"),
    ("AT-060", "建库时间", "libraryPrepTime", ("E01-04",), "STRING", "min", False, "<20"),
    ("AT-061", "支持文库类型", "supportedLibraryType", ("E01-04",), "STRING", "-", False, "单端/双端文库"),
    ("AT-062", "纯化对象", "purificationTarget", ("E01-04",), "STRING", "-", False, "DNA/RNA纯化"),
    ("AT-063", "样本类型", "sampleType", ("E01-04",), "STRING", "-", False, "全血/血清/组织"),
    ("AT-064", "性能特点", "feature", ("E01-04",), "STRING", "-", False, "全波长、多功能"),
    ("AT-065", "波长范围-光吸收", "wavelengthAbs", ("E01-04",), "STRING", "nm", False, "200~1000"),
    ("AT-066", "波长范围-荧光", "wavelengthFl", ("E01-04",), "STRING", "nm", False, "300~800"),
    ("AT-067", "波长范围-化学发光", "wavelengthLum", ("E01-04",), "STRING", "nm", False, "250~800"),
    ("AT-068", "带宽", "bandwidth", ("E01-04",), "STRING", "nm", False, "±4"),
    ("AT-069", "光吸收检测范围", "odRange", ("E01-04",), "STRING", "AU", False, "0~3.0"),
    ("AT-070", "荧光动态范围", "dynamicRangeFl", ("E01-04",), "STRING", "-", False, "≥4个数量级"),
    ("AT-071", "温度控制范围", "tempControl", ("E01-04",), "STRING", "℃", False, "4~50±0.2"),
    ("AT-072", "配套软件", "software", ("E01-04",), "STRING", "-", False, "配套分析软件"),
    # 扫描电镜专属
    ("AT-073", "放大倍数", "magnification", ("E01-04",), "STRING", "×", False, "5~300000"),
    ("AT-074", "加速电压", "accelerationVoltage", ("E01-04",), "STRING", "kV", False, "0.5~30"),
    ("AT-075", "抽真空时间", "pumpDownTime", ("E01-04",), "STRING", "s", False, "<60"),
    ("AT-076", "低真空范围", "lowVacuumRange", ("E01-04",), "STRING", "Pa", False, "10~1330"),
    ("AT-077", "信号采集带宽", "signalBandwidth", ("E01-04",), "STRING", "MHz", False, "20"),
    ("AT-078", "最大样品尺寸", "maxSampleSize", ("E01-04",), "STRING", "mm", False, "Φ200×80"),
    ("AT-079", "样品台行程", "stageTravel", ("E01-04",), "STRING", "mm", False, "X/Y: 150/150"),
    ("AT-080", "成像模式", "imagingMode", ("E01-04",), "STRING", "-", False, "SE/BSE 成像"),
    # 荧光计专属
    ("AT-081", "检测浓度范围", "detectionRange", ("E01-04",), "STRING", "-", False, "10^-15~10^-3 M"),
    ("AT-082", "波长范围", "wavelengthRange", ("E01-04",), "STRING", "nm", False, "230~900"),
    ("AT-083", "样本量", "sampleVolume", ("E01-04",), "STRING", "μL", False, "20~2000"),
    ("AT-084", "光程", "opticalPath", ("E01-04",), "STRING", "mm", False, "5×24×2"),
    ("AT-085", "加热温度", "heatingTemp", ("E01-04",), "STRING", "℃", False, "室温~95±0.5"),
    ("AT-086", "搅拌速度", "stirringSpeed", ("E01-04",), "STRING", "rpm", False, "500~1500"),
    ("AT-087", "光源寿命", "lightSourceLife", ("E01-04",), "STRING", "h", False, "≥5000"),
    ("AT-088", "输入电源", "powerInput", ("E01-04",), "STRING", "-", False, "AC 100~240V"),
    # 运输投送装备专属
    ("AT-089", "容积", "volume", ("E01-07",), "STRING", "L", False, "≥200"),
    ("AT-090", "制冷噪音", "noise", ("E01-07",), "STRING", "dB", False, "<40"),
    ("AT-091", "供电方式", "powerSupply", ("E01-07",), "STRING", "-", False, "车载12V + 市电220V"),
    ("AT-092", "最高速度", "maxSpeed", ("E01-07",), "STRING", "km/h", False, "≥100"),
    ("AT-093", "最大爬坡度", "gradeability", ("E01-07",), "STRING", "°", False, "≥30°"),
    ("AT-094", "涉水深度", "fordingDepth", ("E01-07",), "STRING", "mm", False, "≥500"),
    ("AT-095", "发动机", "engine", ("E01-07",), "STRING", "-", False, "柴油发动机"),
    ("AT-096", "燃油箱容积", "fuelTankVolume", ("E01-07",), "STRING", "L", False, "≥80"),
    ("AT-097", "驱动形式", "driveType", ("E01-07",), "STRING", "-", False, "4×4 全轮驱动"),
    # 其他
    ("AT-098", "电源", "powerSupplyGen", ("E01",), "STRING", "-", False, "AC 220V 50Hz"),
    ("AT-099", "操作系统", "operatingSystem", ("E01-01",), "STRING", "-", False, "Linux 嵌入式"),
    ("AT-100", "主机净重", "mainUnitWeight", ("E01-01",), "STRING", "kg", False, "主机净重约15kg"),
    ("AT-101", "计算模块净重", "computerModuleWeight", ("E01-01",), "STRING", "kg", False, "计算模块净重约5kg"),
]

ATTRIBUTE_KEYS: dict[str, AttributeDef] = {
    code: AttributeDef(code=code, name_zh=zh, name_en=en,
                       applicable_concepts=tuple(cls), data_type=dt, unit=u,
                       required=req, example=ex)
    for code, zh, en, cls, dt, u, req, ex in _STANDARD_ATTRIBUTES + _LONGTAIL_ATTRIBUTES
}


# ============================================================
# 核心校验函数
# ============================================================
def validate_triple(head_code: str, rel_code: str, tail_code: str) -> bool:
    """校验 (head, rel, tail) 是否满足本体 domain→range 约束。

    Args:
        head_code: 头实体的概念类 code（如 "E01-01"）
        rel_code: 关系的英文标识（如 "adopts"）或中文名称（如 "采用"）
        tail_code: 尾实体的概念类 code

    Returns:
        True = 通过校验，可以 MERGE 进 Neo4j
    """
    # 关系 code 查找：支持英文标识、中文名称、或关系编号
    rel_def = RELATION_TYPES.get(rel_code)
    if not rel_def:
        # 尝试英文名 → code
        code = REL_EN_TO_CODE.get(rel_code)
        if code:
            rel_def = RELATION_TYPES.get(code)
    if not rel_def:
        # 尝试中文名 → 英文名 → code
        en = REL_ZH_TO_EN.get(rel_code)
        if en:
            code = REL_EN_TO_CODE.get(en)
            if code:
                rel_def = RELATION_TYPES.get(code)
    if not rel_def:
        # 未知关系 → 保守拒绝（不进图谱）
        return False

    # 实体 code 必须存在于本体
    if head_code not in ENTITY_TYPES or tail_code not in ENTITY_TYPES:
        return False

    return rel_def.validate(head_code, tail_code)


def validate_attribute(attr_code: str, concept_code: str) -> bool:
    """检查某属性是否可用于某概念类（attribute 的 applicable_concepts）。"""
    attr = ATTRIBUTE_KEYS.get(attr_code)
    if not attr:
        return False
    return any(is_descendant(concept_code, c) for c in attr.applicable_concepts)


# ============================================================
# 统计
# ============================================================
def ontology_stats() -> dict:
    """当前本体规模统计。"""
    entity_counts = {}
    for e in ENTITY_TYPES.values():
        entity_counts[e.level] = entity_counts.get(e.level, 0) + 1

    return {
        "entity_types": len(ENTITY_TYPES),
        "entity_by_level": entity_counts,
        "relation_types": len(RELATION_TYPES),
        "relation_by_category": {
            cat: sum(1 for r in RELATION_TYPES.values() if r.category == cat)
            for cat in set(r.category for r in RELATION_TYPES.values())
        },
        "attribute_keys": len(ATTRIBUTE_KEYS),
        "standard_attrs": len(_STANDARD_ATTRIBUTES),
        "longtail_attrs": len(_LONGTAIL_ATTRIBUTES),
    }


if __name__ == "__main__":
    stats = ontology_stats()
    print("📐 装备知识图谱本体统计")
    print("=" * 50)
    print(f"📦 概念类总数: {stats['entity_types']}")
    for lvl, cnt in sorted(stats['entity_by_level'].items()):
        print(f"   {lvl}: {cnt}")
    print(f"\n🔗 关系总数: {stats['relation_types']}")
    for cat, cnt in stats['relation_by_category'].items():
        print(f"   {cat}: {cnt}")
    print(f"\n📋 属性总数: {stats['attribute_keys']} (标准 {stats['standard_attrs']} + 长尾 {stats['longtail_attrs']})")

    # 校验测试
    print("\n🧪 校验测试:")
    tests = [
        ("E01-01", "adopts", "E03-01", True),     # 测序仪 采用 装备原理 ✅
        ("E01-01", "adopts", "E07-01", False),    # 测序仪 采用 防疫任务 ❌
        ("E01-01", "matchedWith", "E02-03", True), # 测序仪 配套 装备部件 ✅
        ("E01-01", "has", "E13-02", True),        # 测序仪 具有 性能指标 ✅
        ("E08-02", "equippedWith", "E01-01", True), # 组织 配备 测序仪 ✅
        ("E08-02", "equippedWith", "E02-03", False), # 组织 配备 部件 ❌
        ("E11-03", "causes", "E11-01", True),     # 媒介 导致 传染病 ✅
        ("E01-01", "未知关系", "E02-03", False),    # 未知关系 ❌
    ]
    for h, r, t, expected in tests:
        result = validate_triple(h, r, t)
        mark = "✅" if result == expected else "❌"
        print(f"  {mark} validate_triple({h:8s}, {r:20s}, {t:8s}) = {result} (预期 {expected})")
