"""物理单位契约测试（KNOWN_ISSUES #19/#26）。

重点覆盖 Codex 对抗审查驳回过的两类错误方案：
- 按优先级静默取一个声明（冲突时会选中错的那个）
- 按 GeneratedBy == 'Epycon' 泛化推定 uV（会误判合法的 mV 文件）
"""
import pytest

from epycon.core.units import (
    UV, MV, NV, COUNTS, UNKNOWN,
    UNITS_CONTRACT_VERSION,
    normalize, resolve, to_mv_factor, resolve_hdf5, resolve_hdf5_detailed,
    channel_units, declarations,
)


class TestNormalize:
    @pytest.mark.parametrize("raw,want", [
        ("uV", UV), ("uv", UV), ("UV", UV), ("  uV  ", UV),
        ("µV", UV),          # U+00B5 MICRO SIGN
        ("μV", UV),          # U+03BC GREEK SMALL LETTER MU
        ("microvolt", UV),
        (b"uV", UV), (b"\xc2\xb5V".decode('utf-8'), UV),
        ("mV", MV), ("millivolt", MV),
        ("nV", NV), ("counts", COUNTS), ("LSb", COUNTS),
    ])
    def test_recognized(self, raw, want):
        assert normalize(raw) == want

    @pytest.mark.parametrize("raw", [None, "", "   ", "volts", "xyz", 42, 3.5])
    def test_unrecognized_returns_none(self, raw):
        """无法识别一律 None——不猜。"""
        assert normalize(raw) is None


class TestResolve:
    def test_consistent_declarations_adopted(self):
        assert resolve(["uV", "uv", "µV"]) == UV

    def test_conflict_returns_unknown(self):
        """冲突必须 unknown，绝不按优先级取第一个（Codex 驳回过该方案）。"""
        assert resolve(["mV", "uV"]) == UNKNOWN
        assert resolve(["uV", "mV"]) == UNKNOWN

    def test_no_declaration_returns_unknown(self):
        assert resolve([]) == UNKNOWN
        assert resolve([None, None]) == UNKNOWN

    def test_unrecognized_skipped_not_treated_as_conflict(self):
        """一个拼错的标签不该把整个文件打成 unknown。"""
        assert resolve(["uV", "bogus", None]) == UV


class TestToMvFactor:
    @pytest.mark.parametrize("units,want", [(UV, 1e-3), (MV, 1.0), (NV, 1e-6)])
    def test_convertible(self, units, want):
        assert to_mv_factor(units) == want

    @pytest.mark.parametrize("units", [COUNTS, UNKNOWN, None, "bogus"])
    def test_not_convertible_returns_none(self, units):
        """None = 不可物理定标。退化为 1.0 正是 #25 overlay 把 µV 当 mV 画的成因。"""
        assert to_mv_factor(units) is None


class TestResolveHdf5:
    def test_new_epycon_file_declares_uv(self):
        assert resolve_hdf5(None, None, ["uV", "uV"],
                            generated_by="Epycon",
                            contract=UNITS_CONTRACT_VERSION) == UV

    def test_legacy_epycon_mv_is_issue19_artifact(self):
        """#19 前的 epycon 文件：Info 标 mV、无契约标记、实为 µV。"""
        assert resolve_hdf5(None, None, ["mV", "mV"],
                            generated_by="Epycon", contract=None) == UV

    def test_contract_marked_mv_is_honored_not_overridden(self):
        """带契约标记的文件声明 mV 就是 mV——legacy 规则不得越界。

        这是 Codex 驳回'GeneratedBy=Epycon 即 uV'泛化推定的核心场景：
        调用方可以合法产出真实 mV 数据的 Epycon 文件。
        """
        assert resolve_hdf5(None, None, ["mV"],
                            generated_by="Epycon",
                            contract=UNITS_CONTRACT_VERSION) == MV

    def test_non_epycon_mv_is_honored(self):
        """第三方 mV 文件不受 legacy 规则影响。"""
        assert resolve_hdf5("mV", None, [], generated_by="SomeOtherTool") == MV
        assert resolve_hdf5(None, "mV", [], generated_by=None) == MV

    def test_root_attr_declaration_is_read(self):
        """root attr 曾被完全无视（#26），必须参与解析。"""
        assert resolve_hdf5("uV", None, [], generated_by=None) == UV

    def test_conflicting_root_and_info_returns_unknown(self):
        """合法调用即可产出 root=mV 与 Info=uV 并存的文件；不得静默取一个。"""
        assert resolve_hdf5("mV", None, ["uV"], generated_by=None) == UNKNOWN

    def test_no_declaration_returns_unknown(self):
        assert resolve_hdf5(None, None, [], generated_by=None) == UNKNOWN

    def test_legacy_rule_does_not_fire_without_epycon(self):
        """非 epycon 的无标记 mV 文件就是 mV。"""
        assert resolve_hdf5(None, None, ["mV"], generated_by="Other") == MV


class TestChannelUnits:
    def test_per_channel_preserved(self):
        assert channel_units(["uV", b"mV", "bogus"]) == [UV, MV, UNKNOWN]

    def test_mixed_units_visible_to_caller(self):
        """混合单位必须能被看见——单个标量表达不了（#26）。"""
        per_ch = channel_units(["uV", "mV"])
        assert len(set(per_ch)) > 1
        assert resolve(["uV", "mV"]) == UNKNOWN


# ========================= Python / JS 契约同步 =========================

class TestPythonJsContractParity:
    """`ui/ecg_viewer.html` 的 Units 是本模块的 JS 镜像，两侧规则必须逐条一致。

    两个运行时各写一份是 h5wasm 前端直读（不经后端）逼出来的，无法避免；
    能做的是让漂移在 CI 立即暴露，而不是等某天渲染出 1000× 的波形。
    GitHub runner（ubuntu-latest）自带 node，故本测试在 CI 真实执行。
    """

    CASES = [
        {'op': 'normalize', 'arg': 'uV'},
        {'op': 'normalize', 'arg': 'µV'},   # U+00B5 MICRO SIGN
        {'op': 'normalize', 'arg': 'μV'},   # U+03BC GREEK SMALL LETTER MU
        {'op': 'normalize', 'arg': ' MV '},
        {'op': 'normalize', 'arg': 'counts'},
        {'op': 'normalize', 'arg': 'bogus'},
        {'op': 'normalize', 'arg': None},
        # bytes/字节串：Python 是 bytes，JS 是 Uint8Array，两侧都须解码而非 str()
        {'op': 'normalize_bytes', 'arg': 'uV'},
        {'op': 'normalize_bytes', 'arg': 'mV'},
        {'op': 'resolve', 'arg': ['uV', 'uv', 'µV']},
        {'op': 'resolve', 'arg': ['mV', 'uV']},
        {'op': 'resolve', 'arg': []},
        {'op': 'resolve', 'arg': ['uV', 'bogus', None]},
        {'op': 'to_mv', 'arg': 'uV'},
        {'op': 'to_mv', 'arg': 'mV'},
        {'op': 'to_mv', 'arg': 'nV'},
        {'op': 'to_mv', 'arg': 'counts'},
        {'op': 'to_mv', 'arg': 'unknown'},
        {'op': 'to_mv', 'arg': None},
        {'op': 'hdf5', 'root': None, 'ds': None, 'info': ['uV'], 'gen': 'Epycon', 'contract': 1},
        {'op': 'hdf5', 'root': None, 'ds': None, 'info': ['mV'], 'gen': 'Epycon', 'contract': None},
        {'op': 'hdf5', 'root': None, 'ds': None, 'info': ['mV'], 'gen': 'Epycon', 'contract': 1},
        {'op': 'hdf5', 'root': 'mV', 'ds': None, 'info': [], 'gen': 'Other', 'contract': None},
        {'op': 'hdf5', 'root': 'mV', 'ds': None, 'info': ['uV'], 'gen': None, 'contract': None},
        {'op': 'hdf5', 'root': None, 'ds': None, 'info': [], 'gen': None, 'contract': None},
        {'op': 'hdf5', 'root': None, 'ds': 'mV', 'info': [], 'gen': None, 'contract': None},
        {'op': 'hdf5', 'root': None, 'ds': None, 'info': ['mV'], 'gen': 'Other', 'contract': None},
        # 数组形态的属性声明（h5py tolist() 后常见），须参与冲突判定
        {'op': 'hdf5', 'root': ['mV'], 'ds': None, 'info': ['uV'], 'gen': None, 'contract': None},
        {'op': 'hdf5', 'root': ['uV'], 'ds': None, 'info': ['uV'], 'gen': None, 'contract': None},
        {'op': 'hdf5', 'root': ['mV', 'uV'], 'ds': None, 'info': [], 'gen': None, 'contract': None},
        # 同值多元素数组：JS 若靠 String(array) 会得到 'mv,mv' 而误判 unknown
        {'op': 'hdf5', 'root': ['mV', 'mV'], 'ds': None, 'info': [], 'gen': None, 'contract': None},
        {'op': 'hdf5', 'root': ['uV', 'uV', 'uV'], 'ds': None, 'info': [], 'gen': None, 'contract': None},
        {'op': 'hdf5', 'root': None, 'ds': None, 'info': ['uV', 'uV'], 'gen': None, 'contract': None},
        {'op': 'hdf5', 'root': None, 'ds': None, 'info': ['uV', 'mV'], 'gen': None, 'contract': None},
        # 推定标记须两侧一致
        {'op': 'hdf5_detailed', 'root': None, 'ds': None, 'info': ['mV'], 'gen': 'Epycon', 'contract': None},
        {'op': 'hdf5_detailed', 'root': None, 'ds': None, 'info': ['uV'], 'gen': 'Epycon', 'contract': 1},
        {'op': 'hdf5_detailed', 'root': 'mV', 'ds': None, 'info': [], 'gen': 'Other', 'contract': None},
    ]

    def _python_result(self, c):
        if c['op'] == 'normalize':
            return normalize(c['arg'])
        if c['op'] == 'normalize_bytes':
            return normalize(c['arg'].encode('utf-8'))
        if c['op'] == 'resolve':
            return resolve(c['arg'])
        if c['op'] == 'to_mv':
            return to_mv_factor(c['arg'])
        if c['op'] == 'hdf5_detailed':
            units, inferred = resolve_hdf5_detailed(
                c['root'], c['ds'], c['info'],
                generated_by=c['gen'], contract=c['contract'])
            return [units, inferred]
        return resolve_hdf5(c['root'], c['ds'], c['info'],
                            generated_by=c['gen'], contract=c['contract'])

    def test_js_mirror_matches_python(self, tmp_path):
        import json
        import shutil
        import subprocess
        from pathlib import Path

        if shutil.which('node') is None:
            pytest.skip('node 不可用，无法校验 JS 镜像')

        html = Path('ui/ecg_viewer.html').read_text(encoding='utf-8')
        start = html.index('const Units = {')
        end = html.index('};', html.index('resolveHdf5(')) + 2
        (tmp_path / 'units.js').write_text(
            html[start:end] + '\nmodule.exports = Units;\n', encoding='utf-8')
        (tmp_path / 'run.js').write_text("""
const Units = require('./units.js');
const cases = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));
console.log(JSON.stringify(cases.map(c => {
    if (c.op === 'normalize') return Units.normalize(c.arg);
    if (c.op === 'normalize_bytes') return Units.normalize(new TextEncoder().encode(c.arg));
    if (c.op === 'resolve') return Units.resolve(c.arg);
    if (c.op === 'to_mv') return Units.toMvFactor(c.arg);
    if (c.op === 'hdf5_detailed') {
        const r = Units.resolveHdf5Detailed(c.root, c.ds, c.info, c.gen, c.contract);
        return [r.units, r.inferred];
    }
    return Units.resolveHdf5(c.root, c.ds, c.info, c.gen, c.contract);
})));
""", encoding='utf-8')
        cases_path = tmp_path / 'cases.json'
        cases_path.write_text(json.dumps(self.CASES), encoding='utf-8')

        proc = subprocess.run(['node', str(tmp_path / 'run.js'), str(cases_path)],
                              capture_output=True, text=True, cwd=str(tmp_path))
        assert proc.returncode == 0, f"node 执行失败: {proc.stderr}"
        js_results = json.loads(proc.stdout)

        mismatches = []
        for c, js in zip(self.CASES, js_results):
            py = self._python_result(c)
            if py != js and not (py is None and js is None):
                mismatches.append(f"{c} -> py={py!r} js={js!r}")
        assert not mismatches, "Python 与 JS 契约漂移:\n" + "\n".join(mismatches)


class TestDeclarationsFlattening:
    """HDF5 属性可能是 ndarray/list —— h5py 读出后常被 tolist() 成 list。

    normalize 只吃标量，若不摊平，`root=["mV"]` 会被当成"未声明"而静默漏掉，
    冲突判定失效（且与 JS 的 decodeAttr 行为不等价）。
    """

    def test_scalar(self):
        assert declarations("uV") == ["uV"]

    def test_bytes_not_split_into_chars(self):
        assert declarations(b"uV") == [b"uV"]

    def test_single_element_list_unwrapped_to_one_declaration(self):
        assert declarations(["mV"]) == ["mV"]

    def test_numpy_array(self):
        import numpy as np
        assert declarations(np.array(["mV"])) == ["mV"]

    def test_multi_element_all_participate(self):
        assert declarations(["mV", "uV"]) == ["mV", "uV"]

    def test_none(self):
        assert declarations(None) == []

    def test_array_shaped_declaration_participates_in_conflict(self):
        """root=["mV"] + Info="uV" 必须判冲突，而不是漏掉 root 后采信 uV。"""
        assert resolve_hdf5(["mV"], None, ["uV"]) == UNKNOWN

    def test_array_shaped_declaration_adopted_when_consistent(self):
        assert resolve_hdf5(["uV"], None, ["uV"]) == UV


class TestInferredFlag:
    """legacy 推定必须可见——该签名不唯一，静默改写等于赌。"""

    def test_legacy_rule_marks_inferred(self):
        units, inferred = resolve_hdf5_detailed(None, None, ["mV"], generated_by="Epycon")
        assert (units, inferred) == (UV, True)

    def test_honest_declaration_not_marked_inferred(self):
        units, inferred = resolve_hdf5_detailed(
            None, None, ["uV"], generated_by="Epycon", contract=UNITS_CONTRACT_VERSION)
        assert (units, inferred) == (UV, False)

    def test_third_party_not_marked_inferred(self):
        units, inferred = resolve_hdf5_detailed("mV", None, [], generated_by="Other")
        assert (units, inferred) == (MV, False)
