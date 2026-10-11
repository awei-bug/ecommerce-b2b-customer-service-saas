# -*- coding: utf-8 -*-
"""Flask CLI for formal tenant delivery onboarding."""
from __future__ import annotations

import json
from pathlib import Path

import click

from flask_shop.tenant_onboarding import (
    DEFAULT_PAY_GUIDE,
    OnboardingError,
    create_formal_tenant,
    export_templates,
    import_initial_data,
    inspect_tenant,
    load_import_rows,
    purge_demo_business,
    write_error_report,
)


def _echo_json(value):
    click.echo(json.dumps(value, ensure_ascii=False, indent=2, default=str))


@click.group("tenant")
def tenant_cli():
    """创建正式租户、导入首批数据并管理演示数据。"""


@tenant_cli.command("create")
@click.option("--slug", required=True, help="团队标识，如 acme-shop。")
@click.option("--name", required=True, help="店铺名称。")
@click.option("--admin-name", default="admin", show_default=True, help="初始管理员账号。")
@click.option("--admin-password", envvar="TENANT_ADMIN_PASSWORD", prompt=True, hide_input=True, confirmation_prompt=True)
@click.option("--admin-nickname", default="店长", show_default=True)
@click.option("--contact-phone", default="")
@click.option("--plan-code", default="pro", show_default=True)
@click.option("--theme", type=click.Choice(["retail", "tea", "fashion", "digital"]), default="retail", show_default=True)
@click.option("--pay-guide", default=DEFAULT_PAY_GUIDE, help="付款说明。")
@click.option("--freight-fee", type=float, default=0, show_default=True)
@click.option("--free-shipping-amount", type=float, default=None)
def create_tenant_command(**kwargs):
    """创建 live 租户、超级管理员和默认运费。"""
    try:
        result = create_formal_tenant(**kwargs)
    except OnboardingError as exc:
        raise click.ClickException(str(exc)) from exc
    _echo_json(result)


@tenant_cli.command("templates")
@click.option("--output-dir", type=click.Path(file_okay=False, path_type=Path), required=True)
def templates_command(output_dir):
    """生成商品、员工、历史订单 CSV 与 Excel 模板。"""
    try:
        result = export_templates(output_dir)
    except (OSError, OnboardingError) as exc:
        raise click.ClickException(str(exc)) from exc
    _echo_json(result)


@tenant_cli.command("import-data")
@click.option("--slug", required=True, help="只允许导入 live 租户。")
@click.option("--file", "file_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.option("--kind", type=click.Choice(["products", "staff", "orders", "all"]), required=True)
@click.option("--dry-run", is_flag=True, help="完整校验后回滚，不写入数据库。")
@click.option("--error-file", type=click.Path(dir_okay=False, path_type=Path), default=None)
def import_data_command(slug, file_path, kind, dry_run, error_file):
    """导入商品库存、员工或历史订单并输出逐行错误报告。"""
    try:
        rows = load_import_rows(file_path, kind)
        result = import_initial_data(slug, rows, dry_run=dry_run)
    except OnboardingError as exc:
        raise click.ClickException(str(exc)) from exc

    if result["errors"]:
        report = error_file or file_path.with_name(f"{file_path.stem}.errors.csv")
        result["error_file"] = write_error_report(result["errors"], report)
    _echo_json(result)
    if result["errors"]:
        raise click.ClickException(f"有 {result['error_count']} 行未导入，请查看错误报告")


@tenant_cli.command("purge-demo-data")
@click.option("--slug", default="demo", show_default=True)
@click.option("--execute", is_flag=True, help="真正执行；省略时只显示待清理数量。")
@click.option("--confirm", default="", help="执行时必须与 --slug 完全一致。")
def purge_demo_data_command(slug, execute, confirm):
    """清理标准演示业务数据；默认只预览且拒绝 live 租户。"""
    if execute and confirm != slug:
        raise click.ClickException("执行清理时 --confirm 必须与 --slug 完全一致")
    try:
        result = purge_demo_business(slug, execute=execute)
    except OnboardingError as exc:
        raise click.ClickException(str(exc)) from exc
    _echo_json(result)


@tenant_cli.command("inspect")
@click.option("--slug", required=True)
def inspect_tenant_command(slug):
    """核对租户模式及员工、商品、订单等初始化数量。"""
    try:
        result = inspect_tenant(slug)
    except OnboardingError as exc:
        raise click.ClickException(str(exc)) from exc
    _echo_json(result)
