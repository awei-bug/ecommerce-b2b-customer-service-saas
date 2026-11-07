"""MySQL 到 PostgreSQL 迁移的数据丢失守卫。

不连接数据库，只验证两个纯判定函数：源端未建模表、未建模列含非空值。
主流程据此拒绝迁移并返回非零退出码。
"""
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "migrate_to_postgres.py"


def _module():
    spec = importlib.util.spec_from_file_location("migrate_to_postgres_guard", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_unmapped_source_tables_are_detected():
    module = _module()
    assert module.find_unmapped_tables(
        ["t_orders", "t_products", "legacy_warehouse"],
        {"t_orders", "t_products"},
    ) == ["legacy_warehouse"]


def test_no_loss_when_all_columns_are_modeled():
    module = _module()
    keep, skip, nonnull = module.classify_source_columns(
        ["id", "name"], {"id", "name"}, [("1", "商品A")]
    )
    assert keep == ["id", "name"]
    assert skip == []
    assert nonnull == 0


def test_nonnull_unmapped_column_is_reported():
    module = _module()
    rows = [("1", "商品A", None), ("2", "商品B", "海关申报值")]
    keep, skip, nonnull = module.classify_source_columns(
        ["id", "name", "customs_declaration"], {"id", "name"}, rows
    )
    assert keep == ["id", "name"]
    assert skip == ["customs_declaration"]
    assert nonnull == 1


def test_all_null_unmapped_column_does_not_count_as_loss():
    module = _module()
    keep, skip, nonnull = module.classify_source_columns(
        ["id", "name", "reserved"], {"id", "name"},
        [("1", "商品A", None), ("2", "商品B", None)],
    )
    assert skip == ["reserved"]
    assert nonnull == 0
