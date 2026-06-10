"""config 双份同步守卫

职责划分（两份并存是有意设计）：
- epycon/config/  包内默认模板，python -m epycon 无环境变量时的 fallback
- config/         根目录运行时配置，CI 与本地运行使用（EPYCON_CONFIG 指向它）

约束：schema.json 必须保持字节语义一致（改一份必须同步另一份）；
两份 config.json 结构可以不同（模板 vs 运行值），但都必须通过 schema 校验。
此测试把"静默漂移"变成"CI 立即报警"。
"""
import json
from pathlib import Path

import jsonschema

ROOT = Path(__file__).parent.parent


def _load(relpath):
    return json.loads((ROOT / relpath).read_text(encoding="utf-8"))


def test_schemas_are_identical():
    assert _load("config/schema.json") == _load("epycon/config/schema.json"), (
        "config/schema.json 与 epycon/config/schema.json 漂移了——请同步修改两份"
    )


def test_both_configs_validate_against_schema():
    schema = _load("epycon/config/schema.json")
    for cfg_path in ("config/config.json", "epycon/config/config.json"):
        jsonschema.validate(_load(cfg_path), schema)
