"""物理单位契约：声明的规范化与采信规则（唯一实现）。

背景（KNOWN_ISSUES #19/#25/#26/#27/#28）：epycon 写出的 HDF5 曾把 µV 数据标为 mV
（量纲链 raw_int × resolution(78 nV/LSb) ÷ factor(1000) = µV，标签却写 mV）。写入侧已于
2026-07-16 修正，但读取侧此前**从不读文件里的声明**——恒取硬编码默认值，前端再按幅度
猜（`dataRange > 50 ? 0.001 : 1.0`），CSV/npz 各写各的量纲。错标与猜测长期两两抵消，
掩盖了"全仓库没有单位契约"这一根因。

本模块是该契约的唯一权威：谁声明、如何规范化、多处声明冲突时怎么办。

设计要点（其中 2/3 由 Codex 对抗审查逐条驳回早期方案后定型）：
- **一致才采信，冲突即 unknown**——不按优先级静默取一个。`HDFPlanter` 允许调用方分别传
  任意 root attributes 与逐通道 units，合法调用即可产出 `root=mV` 与 `Info=uV` 并存的文件；
  "取第一个"会静默选中错的那个、重新制造 1000× 误标。
- **`GeneratedBy == 'Epycon'` 不足以推定 uV**——`HDFPlanter` 无条件写该属性，而 `units`/
  `factor` 是公开 kwargs，调用方可以合法产出"真实 mV 数据 + Info.Units=mV"的文件。
  故新文件改用显式契约标记（`UNITS_CONTRACT_ATTR`），不靠推断。
- **legacy 窄规则**见 `resolve_hdf5`：只对 #19 的**已证实坏签名**生效，不是泛化推定。
- **unknown 必须向上传播**，由消费方拒绝物理定标或要求用户确认，**不要猜**。
"""
from typing import Iterable, List, Optional

# 规范名。counts = 原始整数计数（extraction 的 raw_counts 模式），无物理量纲。
UV = 'uV'
MV = 'mV'
NV = 'nV'
COUNTS = 'counts'
UNKNOWN = 'unknown'

# 新版 HDF5 的契约标记：存在且为真 => Info.Units 如实声明，可直接采信。
# 缺失 => 文件早于本契约，须走 resolve_hdf5 的 legacy 判定。
UNITS_CONTRACT_ATTR = 'EpyconUnitsContract'
UNITS_CONTRACT_VERSION = 1

# 书写形式 -> 规范名。µ 有两个常见码位：U+00B5 MICRO SIGN 与 U+03BC GREEK SMALL LETTER MU。
_ALIASES = {
    'uv': UV, 'µv': UV, 'μv': UV, 'microvolt': UV, 'microvolts': UV,
    'mv': MV, 'millivolt': MV, 'millivolts': MV,
    'nv': NV, 'nanovolt': NV, 'nanovolts': NV,
    'counts': COUNTS, 'count': COUNTS, 'lsb': COUNTS, 'adu': COUNTS,
}

# 规范名 -> 换算到 mV 的因子。counts 无量纲，不可换算，故不在表内。
_TO_MV = {UV: 1e-3, MV: 1.0, NV: 1e-6}


def normalize(value) -> Optional[str]:
    """把任意书写形式的单位声明规范化为规范名；无法识别返回 None。

    接受 str / bytes / numpy bytes；None、空串、未知写法一律返回 None（不猜）。
    """
    if value is None:
        return None
    if isinstance(value, bytes):
        try:
            value = value.decode('utf-8', errors='replace')
        except Exception:
            return None
    if not isinstance(value, str):
        return None
    return _ALIASES.get(value.strip().lower())


def declarations(value) -> List:
    """把一处属性值摊平成"若干条声明"。

    HDF5 属性可能是标量，也可能是 ndarray/list（h5py 读出后常被 `.tolist()` 成 list）。
    单元素序列 = 一条声明；多元素序列 = **多条**声明，须各自参与冲突判定，
    不能只看第一个——那又回到"按优先级静默取一个"的老路。
    bytes 是字节串不是序列，必须先挡掉，否则会被逐字节摊开。
    """
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return list(value)
    if hasattr(value, 'tolist'):          # numpy 标量/数组
        flat = value.tolist()
        return flat if isinstance(flat, list) else [flat]
    return [value]


def resolve(decls: Iterable) -> str:
    """多处声明 -> 单一结论。

    一致才采信；**冲突或无任何可识别声明一律返回 `UNKNOWN`**，绝不按优先级取一个。
    无法识别的声明按"未声明"处理（跳过），不参与冲突判定——否则一个拼错的标签
    就能把整个文件打成 unknown。
    """
    flat = []
    for d in decls:
        flat.extend(declarations(d))
    seen = {n for n in (normalize(d) for d in flat) if n is not None}
    if len(seen) == 1:
        return seen.pop()
    return UNKNOWN


def to_mv_factor(units: Optional[str]) -> Optional[float]:
    """规范名 -> 换算到 mV 的乘法因子；unknown/counts/无法识别返回 None。

    返回 None 表示**不可做物理定标**，消费方应拒绝绘制物理刻度或要求用户确认，
    不得退化为 1.0 —— 那正是 #25 overlay 把 µV 当 mV 画的成因。
    """
    return _TO_MV.get(normalize(units) or units)


def resolve_hdf5_detailed(root_units, dataset_units, info_units: Iterable,
                          generated_by=None, contract=None):
    """同 `resolve_hdf5`，但返回 `(units, inferred)`。

    `inferred=True` 表示结论来自 legacy 窄规则的**推定**而非文件的如实声明——
    消费方必须向用户明示"单位系按旧版约定推定"，不得当作确证。
    该签名（Epycon + 无契约标记 + mV）**不唯一**：历史上直接用 `HDFPlanter` 写入真实
    mV 数据的调用方会产生同样的签名。故推定必须可见，不能静默改写。
    """
    declared = resolve(list(info_units) + [root_units, dataset_units])
    has_contract = bool(contract)
    is_epycon = (normalize_generated_by(generated_by) == 'epycon')

    if not has_contract and is_epycon and declared == MV:
        return UV, True
    return declared, False


def resolve_hdf5(root_units, dataset_units, info_units: Iterable,
                 generated_by=None, contract=None) -> str:
    """解析 HDF5 的单位声明（root attr / Data attr / Info 逐通道）。

    Args:
        root_units: 根属性 `units`（多数文件没有）
        dataset_units: Data 数据集属性 `units`
        info_units: Info 数据集的逐通道 Units
        generated_by: 根属性 `GeneratedBy`
        contract: 根属性 `EpyconUnitsContract`（新版写入侧落的契约标记）

    Returns:
        规范名，或 `UNKNOWN`（无声明 / 声明冲突 / 逐通道单位不一致）。

    **legacy 窄规则**：`GeneratedBy == 'Epycon'` + **无契约标记** + 声明恰为 `mV`
    => 判 `uV`。依据：这是 #19 的已证实坏签名——`conversion.py` 是本仓库 `HDFPlanter`
    的唯一生产调用方，其管线（LogParser ×resolution 得 nV，planter ÷factor(1000)）
    结构上只可能产出 µV，故 epycon 产出物上的 `mV` 标签必为 #19 的误标。
    该规则**只对这一个签名生效**，不是"GeneratedBy=Epycon 即 uV"的泛化推定：
    带契约标记的新文件一律以声明为准，声明 mV 就是 mV。

    **该签名不唯一**，故推定必须对用户可见——需要区分"声明"与"推定"时用
    `resolve_hdf5_detailed`。
    """
    return resolve_hdf5_detailed(root_units, dataset_units, info_units,
                                 generated_by, contract)[0]


def normalize_generated_by(value) -> Optional[str]:
    """规范化 `GeneratedBy` 以便比较（大小写/bytes 无关）。"""
    if isinstance(value, bytes):
        value = value.decode('utf-8', errors='replace')
    if not isinstance(value, str):
        return None
    return value.strip().lower()


def channel_units(info_units: Iterable) -> List[str]:
    """Info 的逐通道 Units -> 逐通道规范名列表（无法识别的位置为 `UNKNOWN`）。

    Info 允许逐通道混合单位，单个标量表达不了——消费方遇到混合单位时
    不得做统一物理定标（见 #26）。
    """
    return [normalize(u) or UNKNOWN for u in info_units]
