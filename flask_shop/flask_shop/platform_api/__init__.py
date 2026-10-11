"""
平台侧最小能力（L0）：租户开通。

鉴权：请求头 X-Platform-Key 必须等于环境变量 PLATFORM_BOOTSTRAP_KEY。
正式运营中台上线后替换为 platform admin JWT。
"""
import os
import re

from flask import Blueprint, request

from flask_shop import db, models
from flask_shop.utils.audit import write_audit

platform_bp = Blueprint('platform', __name__, url_prefix='/api/p')

SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$')


def _check_platform_key():
    from flask import current_app
    import hmac
    expected = (
        current_app.config.get('PLATFORM_BOOTSTRAP_KEY')
        or os.getenv('PLATFORM_BOOTSTRAP_KEY', '')
        or ''
    )
    if not expected:
        return False, {'status': 503, 'msg': '未配置 PLATFORM_BOOTSTRAP_KEY，拒绝开通'}
    got = request.headers.get('X-Platform-Key') or ''
    if not hmac.compare_digest(str(got), str(expected)):
        return False, {'status': 401, 'msg': '平台密钥无效'}
    return True, None


@platform_bp.route('/health/')
def p_health():
    return {'status': 200, 'msg': 'platform ok'}


@platform_bp.route('/tenants/', methods=['POST'])
def create_tenant():
    """
    开通租户 + 管理员。
    body: {
      name, slug,
      admin_name, admin_password,
      admin_phone?, admin_email?,
      plan_code?
    }
    Header: X-Platform-Key
    """
    ok, err = _check_platform_key()
    if not ok:
        return err

    body = request.get_json(silent=True) or {}
    name = (body.get('name') or '').strip()
    slug = (body.get('slug') or '').strip().lower()
    admin_name = (body.get('admin_name') or '').strip()
    admin_password = body.get('admin_password') or ''
    plan_code = (body.get('plan_code') or 'free').strip()

    if not name or not slug or not admin_name or not admin_password:
        return {'status': 400, 'msg': 'name/slug/admin_name/admin_password 必填'}
    if not SLUG_RE.match(slug):
        return {'status': 400, 'msg': 'slug 仅允许小写字母数字与中划线，长度 3～32'}
    if len(admin_password) < 8:
        return {'status': 400, 'msg': '管理员密码至少 8 位'}

    if models.Tenant.query.filter_by(slug=slug).first():
        return {'status': 400, 'msg': 'slug 已存在'}

    tenant = models.Tenant(name=name, slug=slug, status=1, plan_code=plan_code)
    db.session.add(tenant)
    db.session.flush()

    # 绑定平台菜单模板（若已有）
    menus = models.Menu.query.all()
    role = models.Role(tenant_id=tenant.id, name='超级管理员', desc=f'{name}全部权限')
    if menus:
        role.menus = list(menus)
    db.session.add(role)
    db.session.flush()

    # 租户内管理员名唯一
    exists = models.User.query.filter_by(tenant_id=tenant.id, name=admin_name).first()
    if exists:
        db.session.rollback()
        return {'status': 400, 'msg': '管理员账号已存在'}

    user = models.User(
        tenant_id=tenant.id,
        name=admin_name,
        nick_name=body.get('admin_nick') or f'{name}管理员',
        phone=body.get('admin_phone'),
        email=body.get('admin_email'),
        role_id=role.id,
    )
    user.password = admin_password
    db.session.add(user)
    db.session.commit()

    write_audit(
        action='platform.tenant.create',
        resource_type='tenant',
        resource_id=tenant.id,
        detail=f'slug={slug} admin={admin_name}',
        tenant_id=tenant.id,
        actor_type='platform',
        actor_id=0,
    )

    return {
        'status': 200,
        'msg': '租户开通成功',
        'data': {
            'tenant': tenant.to_dict(),
            'admin': {'id': user.id, 'name': user.name, 'role_id': role.id},
        }
    }


@platform_bp.route('/tenants/', methods=['GET'])
def list_tenants():
    ok, err = _check_platform_key()
    if not ok:
        return err
    rows = models.Tenant.query.order_by(models.Tenant.id.desc()).limit(200).all()
    return {'status': 200, 'msg': 'ok', 'data': [t.to_dict() for t in rows]}


@platform_bp.route('/tenants/<int:tid>/status/', methods=['POST'])
def set_tenant_status(tid):
    """body: { status: 0|1 } 停用/启用"""
    ok, err = _check_platform_key()
    if not ok:
        return err
    body = request.get_json(silent=True) or {}
    status = body.get('status')
    if status not in (0, 1, '0', '1'):
        return {'status': 400, 'msg': 'status 须为 0 或 1'}
    tenant = models.Tenant.query.get(tid)
    if not tenant:
        return {'status': 404, 'msg': '租户不存在'}
    tenant.status = int(status)
    db.session.commit()
    write_audit(
        action='platform.tenant.status',
        resource_type='tenant',
        resource_id=tid,
        detail=f'status={tenant.status}',
        tenant_id=tid,
        actor_type='platform',
        actor_id=0,
    )
    return {'status': 200, 'msg': '已更新', 'data': tenant.to_dict()}
