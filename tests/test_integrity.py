"""core/integrity.py 测试套件

覆盖三类事实：
1. 逐通道测量（内容指纹、零占比、冻结占比、轨顶占比）
2. 重复通道识别 —— 名称是主张，样点才是证据
3. 肢导联恒等式，含其对 I/II 互换失效的已知盲区

用例取自一份 WorkMate x64 study 里真实遇到的两种情况：名为 HIS 的通道装着 LBB 的样点，
以及索引标为单极的导出页装着同一导联的双极样点。
"""
import numpy as np
import pytest

from epycon.core.integrity import (
    channel_digest,
    channel_facts,
    check_limb_identities,
    inspect_channels,
    summarise,
)


@pytest.fixture
def limb_leads():
    """六个肢导联，其中四个由 I、II 精确导出 —— 与记录仪的行为一致。"""
    rng = np.random.default_rng(20260825)
    one, two = rng.normal(size=2000), rng.normal(size=2000)
    return {
        "I": one, "II": two, "III": two - one,
        "aVR": -(one + two) / 2, "aVL": one - two / 2, "aVF": two - one / 2,
    }


@pytest.fixture
def recording(limb_leads):
    """12 个诚实通道 + 一对重复（HIS 装的是 LBB）+ 一个从未接入的 STIM。"""
    rng = np.random.default_rng(7)
    n = 2000
    tip, ring = rng.normal(size=n) * 30, rng.normal(size=n) * 20
    names = [*limb_leads, "u+LBB", "u-LBB", "STIM", "u+HIS", "u-HIS"]
    values = np.column_stack([*limb_leads.values(), tip, ring, np.zeros(n), tip, ring])
    return values, names


def test_channel_digest_is_content_based_not_identity_based():
    values = np.arange(64, dtype=float)
    assert channel_digest(values) == channel_digest(values.copy())
    assert channel_digest(values) != channel_digest(values + 1)


def test_channel_facts_measure_dead_frozen_and_railed_inputs():
    dead = channel_facts(np.zeros(1000), name="STIM")
    assert dead["zero_fraction"] == 1.0
    assert dead["frozen_fraction"] == 1.0
    assert dead["sd"] == 0.0

    live = channel_facts(np.sin(np.linspace(0, 20, 1000)), name="u+LBB")
    assert live["zero_fraction"] < 0.01
    assert live["frozen_fraction"] < 0.01
    assert live["rail_fraction"] < 0.01


def test_inspect_channels_names_the_original_of_each_duplicate(recording):
    values, names = recording
    facts = {item["name"]: item for item in inspect_channels(values, names)}
    assert facts["u+HIS"]["duplicate_of"] == "u+LBB"
    assert facts["u-HIS"]["duplicate_of"] == "u-LBB"
    assert facts["u+LBB"]["duplicate_of"] is None
    assert facts["I"]["observations"] == []


def test_inspect_channels_flags_a_channel_that_was_never_connected(recording):
    values, names = recording
    facts = {item["name"]: item for item in inspect_channels(values, names)}
    assert "dead: never connected" in facts["STIM"]["observations"]


def test_summarise_counts_distinct_signals_not_channels(recording):
    values, names = recording
    report = summarise(inspect_channels(values, names))
    assert report["n_channels"] == 11
    assert report["n_distinct_signals"] == 9        # 两对重复各少算一个
    assert report["duplicates"] == {"u+HIS": "u+LBB", "u-HIS": "u-LBB"}
    assert set(report["flagged"]) == {"STIM", "u+HIS", "u-HIS"}


def test_thresholds_are_arguments_so_a_caller_can_set_its_own():
    held = np.repeat(np.arange(10, dtype=float), 100)   # 阶梯保持，冻结占比 0.99
    frozen = "frozen: held or disconnected"
    strict = inspect_channels([held], ["ring"], frozen_fraction=0.5)[0]
    loose = inspect_channels([held], ["ring"], frozen_fraction=0.999)[0]
    assert frozen in strict["observations"]
    assert frozen not in loose["observations"]


def test_inspect_channels_rejects_a_name_count_that_does_not_match():
    with pytest.raises(ValueError, match="2 channels but 1 names"):
        inspect_channels(np.zeros((10, 2)), ["only-one"])


def test_limb_identities_are_exact_when_the_recorder_derives_them(limb_leads):
    result = check_limb_identities(limb_leads)
    assert result["derived"]
    assert result["worst"] == pytest.approx(0.0, abs=1e-12)


def test_limb_identities_are_blind_to_a_swap_between_I_and_II(limb_leads):
    """这是刻意记录的盲区：互换 I、II 后重新导出其余四个，恒等式依旧成立。"""
    one, two = limb_leads["II"], limb_leads["I"]
    swapped = {
        "I": one, "II": two, "III": two - one,
        "aVR": -(one + two) / 2, "aVL": one - two / 2, "aVF": two - one / 2,
    }
    assert check_limb_identities(swapped)["holds"]
    assert check_limb_identities(swapped)["blind_to"] == "a swap between leads I and II"


def test_limb_identities_catch_a_lead_that_does_not_belong(limb_leads):
    corrupted = dict(limb_leads)
    corrupted["aVR"] = -corrupted["aVR"]
    result = check_limb_identities(corrupted)
    assert not result["holds"]
    assert result["residual"]["aVR = -(I + II) / 2"] > 0.05


def test_limb_identities_report_which_leads_are_missing():
    with pytest.raises(KeyError, match="aVF"):
        check_limb_identities({"I": np.zeros(4), "II": np.zeros(4), "III": np.zeros(4),
                               "aVR": np.zeros(4), "aVL": np.zeros(4)})
