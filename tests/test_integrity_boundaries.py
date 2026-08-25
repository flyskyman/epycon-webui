"""core/integrity.py 输入域边界矩阵

test_integrity.py 测"正常输入 → 结果正确"；本文件只测一件事：**畸形或退化输入下不得给出假通过**。
四轮逐条修补（NaN、列切片、长度 1、空串名）说明盲区是整片输入域而非散点，故按轴枚举一次关掉：

- 容器形状轴：inspect_channels 收到的是 2-D 数组、1-D 通道序列，还是被误读的其它形状
- 单通道形状轴：channel_facts 收到的是向量、块，还是标量
- 值域轴：NaN / inf / 整型 / 布尔 / float32 / 常数 / 单样点 / 空
- 名称轴：重名、空串、非 list 容器
- 肢导联轴：容器类型、形状、非有限值、多余键、标量
"""
import numpy as np
import pytest

from epycon.core.integrity import (
    channel_facts,
    check_limb_identities,
    inspect_channels,
    summarise,
)

N = 400


@pytest.fixture
def signal():
    return np.random.default_rng(0).normal(size=N)


@pytest.fixture
def leads():
    rng = np.random.default_rng(1)
    one, two = rng.normal(size=N), rng.normal(size=N)
    return {"I": one, "II": two, "III": two - one, "aVR": -(one + two) / 2, "aVL": one - two / 2, "aVF": two - one / 2}


# ------------------------- 容器形状轴：inspect_channels -------------------------

@pytest.mark.parametrize("build, message", [
    (lambda s: s, "must be 2-D"),                                       # 1-D 数组曾被拆成 n 个单样点通道
    (lambda s: s.tolist(), "single number"),                            # 平铺数字列表同上
    (lambda s: np.stack([s, s + 1], axis=1)[:, :, None], "must be 2-D"),  # 3-D
    (lambda s: [np.stack([s, s + 1], axis=1)], "one-dimensional"),      # 一个 (n,2) 块当"一条通道"曾被 ravel 成 2n 样点
], ids=["1-D array", "flat list", "3-D array", "(n,2) block as one channel"])
def test_misread_containers_are_refused_not_silently_split(signal, build, message):
    with pytest.raises(ValueError, match=message):
        inspect_channels(build(signal))


@pytest.mark.parametrize("build, n_channels, n_samples", [
    (lambda s: np.stack([s, s + 1], axis=1), 2, N),          # 2-D，一列一通道
    (lambda s: s.reshape(-1, 1), 1, N),                      # 单列 2-D
    (lambda s: [s, s + 1], 2, N),                            # 1-D 通道列表
    (lambda s: [s.reshape(-1, 1), s + 1], 2, N),             # 列切片作为通道
    (lambda s: [s[:10], s], 2, 10),                          # 不等长通道彼此独立
    (lambda s: np.zeros((0, 3)), 3, 0),                      # 零样点的三条通道
    (lambda s: [], 0, None),                                 # 没有通道
], ids=["2-D", "2-D single column", "list of 1-D", "list with (n,1)", "ragged", "(0,3)", "empty list"])
def test_legitimate_containers_keep_their_shape(signal, build, n_channels, n_samples):
    facts = inspect_channels(build(signal))
    assert len(facts) == n_channels
    if n_samples is not None:
        assert facts[0]["n_samples"] == n_samples


# ------------------------- 单通道形状轴：channel_facts -------------------------

@pytest.mark.parametrize("shape", [(N, 1), (1, N), (N,)])
def test_channel_facts_accept_any_vector_shape(signal, shape):
    assert channel_facts(signal.reshape(shape))["n_samples"] == N


def test_channel_facts_refuse_a_block(signal):
    with pytest.raises(ValueError, match="one-dimensional"):
        channel_facts(np.stack([signal, signal + 1], axis=1))


# ------------------------- 值域轴 -------------------------

def _with(signal, **at):
    out = signal.copy()
    for index, value in at.items():
        out[int(index[1:])] = value
    return out


@pytest.mark.parametrize("build, expected", [
    (lambda s: s, []),
    (lambda s: (s * 300).astype(np.int16), []),
    (lambda s: s.astype(np.float32), []),
    (lambda s: _with(s, i3=np.inf), ["0.2% of samples are not finite"]),
    (lambda s: _with(s, i3=np.inf, i9=np.nan), ["0.5% of samples are not finite"]),
    (lambda s: np.full(N, np.inf), ["dead: never connected", "100.0% of samples are not finite"]),
    (lambda s: np.full(N, np.nan), ["dead: never connected", "100.0% of samples are not finite"]),
    (lambda s: np.zeros(N), ["dead: never connected", "clipped: resting on a repeated extreme"]),
    (lambda s: np.full(N, 5.0), ["frozen: held or disconnected", "clipped: resting on a repeated extreme"]),
    (lambda s: s > 0, ["clipped: resting on a repeated extreme"]),   # 0/1 信号确实全部贴在自己的两个极值上
    (lambda s: np.array([5.0, 5.0]), ["frozen: held or disconnected", "clipped: resting on a repeated extreme"]),
    (lambda s: np.array([1.0, 2.0]), []),
    (lambda s: np.array([5.0]), []),                                  # 单样点：无相邻对、极值只出现一次——无证据
    (lambda s: np.array([]), ["dead: never connected", "100.0% of samples are not finite"]),
    (lambda s: np.array([np.nan]), ["dead: never connected", "100.0% of samples are not finite"]),
], ids=["normal", "int16", "float32", "one inf", "inf+nan", "all inf", "all nan", "zeros", "constant",
        "bool", "two equal", "two distinct", "single sample", "empty", "single nan"])
def test_value_domain_observations(signal, build, expected):
    assert inspect_channels([build(signal)])[0]["observations"] == expected


def test_no_statistic_is_nan_for_any_value_domain_input(signal):
    """facts 字典里不得出现 NaN：调用方会做 >= 比较和 JSON 序列化。"""
    for column in (signal, _with(signal, i3=np.nan), np.full(N, np.nan), np.array([]), np.array([np.inf])):
        facts = channel_facts(column)
        for key in ("sd", "zero_fraction", "frozen_fraction", "rail_fraction", "nonfinite_fraction"):
            assert np.isfinite(facts[key]), (key, column)


# ------------------------- 名称轴 -------------------------

def test_duplicate_names_are_refused_because_reports_key_by_name(signal):
    with pytest.raises(ValueError, match="unique"):
        inspect_channels([signal, signal + 1], names=["a", "a"])


@pytest.mark.parametrize("names", [("x", "y"), np.array(["x", "y"]), ["", "y"], [0, 1]],
                         ids=["tuple", "ndarray", "empty string", "ints"])
def test_name_containers_and_odd_labels_are_accepted(signal, names):
    facts = inspect_channels([signal, signal.copy()], names=names)
    assert facts[1]["duplicate_of"] == facts[0]["name"]
    assert summarise(facts)["duplicates"] == {facts[1]["name"]: facts[0]["name"]}


# ------------------------- 肢导联轴 -------------------------

@pytest.mark.parametrize("transform, holds, derived", [
    (lambda L: {k: v.tolist() for k, v in L.items()}, True, True),
    (lambda L: {k: v.reshape(2, -1) for k, v in L.items()}, True, True),        # 形状不改变逐样点关系
    (lambda L: {**L, "aVF": L["aVF"].reshape(-1, 1)}, True, True),
    (lambda L: {**L, "extra": np.zeros(3)}, True, True),                         # 多余键不参与，也不触发长度校验
    (lambda L: {**L, "aVF": _with(L["aVF"], i0=np.inf)}, False, False),
    (lambda L: {**L, "aVF": _with(L["aVF"], i0=-np.inf)}, False, False),
    (lambda L: {k: np.full(N, np.nan) for k in L}, False, False),
    (lambda L: {k: (v * 1000).astype(np.int32) for k, v in L.items()}, False, False),  # 截断破坏恒等式
], ids=["lists", "(2,n/2)", "(n,1) lead", "extra key", "+inf", "-inf", "all nan", "int truncation"])
def test_limb_domain_never_passes_without_evidence(leads, transform, holds, derived):
    result = check_limb_identities(transform(leads))
    assert result["holds"] is holds
    assert result["derived"] is derived


@pytest.mark.parametrize("bad", [np.float64(1.0), None, np.array([]), np.zeros(N - 1)],
                         ids=["scalar", "None", "empty", "shorter"])
def test_limb_leads_that_carry_no_matching_samples_are_refused(leads, bad):
    with pytest.raises(ValueError, match="nonzero length"):
        check_limb_identities({**leads, "aVF": bad})


def test_flat_leads_satisfy_every_identity_but_prove_nothing(leads):
    """六条全零导联让四条恒等式平凡成立；这不是"记录仪导出了从属导联"的证据。"""
    flat = check_limb_identities({k: np.zeros(N) for k in leads})
    assert flat["holds"] and not flat["informative"] and not flat["derived"]

    # 只要 I、II 之一有变化，恒等式就非平凡：I 平、II 活时从属导联随 II 变化，derived 仍成立
    two = leads["II"]
    one_flat = {"I": np.zeros(N), "II": two, "III": two, "aVR": -two / 2, "aVL": -two / 2, "aVF": two}
    assert check_limb_identities(one_flat)["derived"]


def test_derived_presumes_float64_and_is_not_a_dtype_test(leads):
    """三条恒等式含 /2：整型或 float32 存储各留一份残差，derived 永远为假，不论记录仪导得多忠实。
    不调容差——容差是调用方按 LSB 设的，这里把代价钉成断言而不是藏起来。"""
    # float64 缩放后浮点非结合性留下 ~1e-14 残差，1e-9 阈值吸收得了它，吸收不了 float32 的 ~1e-7
    scaled = check_limb_identities({k: v * 100 for k, v in leads.items()})
    assert scaled["derived"] and 0 < scaled["worst"] < 1e-9

    float32 = check_limb_identities({k: v.astype(np.float32) for k, v in leads.items()})
    assert float32["holds"] and not float32["derived"]
    assert 1e-9 < float32["worst"] < 1e-6

    int16 = {k: (v * 1000).astype(np.int16) for k, v in leads.items()}   # 截断：残差恰为 1.5 LSB
    assert check_limb_identities(int16)["worst"] == 1.5
    assert not check_limb_identities(int16, tolerance=1.5)["derived"]
    assert check_limb_identities(int16, tolerance=1.5)["holds"]
    assert not check_limb_identities(int16, tolerance=1.0)["holds"]
