"""
B 端接口级 RBAC（动作级细拆）

两层：
  1) 菜单 path：控制前端侧栏可见（role.menus）
  2) 动作码 perm_codes：控制接口能否执行（role.perm_codes JSON）

超级管理员（角色名含「超级」/admin）：全部放行。

若 perm_codes 为空：回退到「菜单 path → 动作」宽松映射（兼容旧数据）。
"""
import json
from functools import wraps

from flask import g

from flask_shop import models

# 全部已知动作码（文档与种子用）
ALL_ACTION_CODES = [
    'order:read',
    'order:create',
    'order:mark_paid',
    'order:ship',
    'order:cancel',
    'order:complete',
    'order:refund',
    'order:export',
    'product:read',
    'product:write',
    'category:write',
    'user:read',
    'user:write',
    'role:read',
    'role:write',
    'report:read',
    'shipment:read',
    'shipment:write',
]

# 旧数据回退：仅有菜单 path 时，按 path 推导动作（偏宽松）
MENU_PATH_TO_ACTIONS = {
    'order_list': [
        'order:read', 'order:create', 'order:mark_paid', 'order:ship',
        'order:cancel', 'order:complete', 'order:refund', 'order:export',
    ],
    'orders': ['order:read'],
    'product_list': ['product:read', 'product:write'],
    'goods': ['product:read'],
    'group_list': ['product:read', 'category:write'],
    'attribute_list': ['product:read', 'category:write'],
    'user_list': ['user:read', 'user:write'],
    'role_list': ['role:read', 'role:write'],
    'author_list': ['role:read'],
    'data_list': ['report:read'],
    'reports': ['report:read'],
    'shipment_list': ['shipment:read', 'shipment:write'],
}

# 角色模板（种子）
ROLE_TEMPLATES = {
    '店员': {
        'desc': '看单、确认收款、发货；不可管员工、不可退款',
        'menu_paths': {
            'goods', 'product_list', 'group_list', 'attribute_list',
            'orders', 'order_list', 'reports', 'data_list', 'shipment_list',
        },
        'perm_codes': [
            'order:read', 'order:mark_paid', 'order:ship', 'order:complete',
            'order:export', 'product:read', 'report:read',
            'shipment:read', 'shipment:write',
        ],
    },
    '仓管': {
        'desc': '仅履约：查看订单与发货',
        'menu_paths': {'orders', 'order_list', 'shipment_list'},
        'perm_codes': [
            'order:read', 'order:ship', 'order:complete',
            'shipment:read', 'shipment:write',
        ],
    },
    '运营': {
        'desc': '商品与数据，只读订单',
        'menu_paths': {
            'goods', 'product_list', 'group_list', 'attribute_list',
            'orders', 'order_list', 'reports', 'data_list', 'shipment_list',
        },
        'perm_codes': [
            'product:read', 'product:write', 'category:write',
            'order:read', 'order:export', 'report:read',
            'shipment:read',
        ],
    },
    '客服': {
        'desc': '订单查询与售后处理',
        'menu_paths': {'orders', 'order_list', 'shipment_list'},
        'perm_codes': [
            'order:read', 'order:cancel', 'order:refund', 'order:export',
            'shipment:read', 'shipment:write',
        ],
    },
}


def _is_super_role(role):
    if not role:
        return False
    name = (role.name or '')
    return name in ('超级管理员', 'admin', 'Admin') or '超级' in name


def _parse_perm_codes(role):
    raw = getattr(role, 'perm_codes', None) or ''
    if not raw:
        return None  # 表示未配置，走菜单回退
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(data, list):
            return set(str(x) for x in data)
    except Exception:
        pass
    return set()


def get_staff_role(staff_id, tenant_id):
    user = models.User.query.filter_by(id=staff_id, tenant_id=tenant_id).first()
    if not user:
        return None, None
    return user, user.role


def get_staff_menu_paths(staff_id, tenant_id):
    user, role = get_staff_role(staff_id, tenant_id)
    if not user or not role:
        return set(), False
    if _is_super_role(role):
        return set(), True
    paths = {m.path for m in (role.menus or []) if m.path}
    return paths, False


def get_staff_action_codes(staff_id, tenant_id):
    """
    返回 (codes:set|None, is_super:bool)
    is_super=True 时 codes 忽略。
    """
    user, role = get_staff_role(staff_id, tenant_id)
    if not user or not role:
        return set(), False
    if _is_super_role(role):
        return set(ALL_ACTION_CODES), True

    codes = _parse_perm_codes(role)
    if codes is not None:
        return codes, False

    # 回退：由菜单 path 推导
    derived = set()
    for m in (role.menus or []):
        if m.path and m.path in MENU_PATH_TO_ACTIONS:
            derived.update(MENU_PATH_TO_ACTIONS[m.path])
    return derived, False


def staff_has_permission(permission, mode='any'):
    """
    permission: 动作码如 'order:ship'，或菜单 path（兼容），或列表
    """
    staff_id = getattr(g, 'staff_id', None)
    tenant_id = getattr(g, 'tenant_id', None)
    if not staff_id or not tenant_id:
        return False

    codes, is_super = get_staff_action_codes(staff_id, tenant_id)
    if is_super:
        return True

    items = permission if isinstance(permission, (list, tuple, set)) else [permission]
    required = []
    for p in items:
        p = str(p)
        # 兼容旧调用：若传的是菜单 path，展开
        if p in MENU_PATH_TO_ACTIONS and ':' not in p:
            required.extend(MENU_PATH_TO_ACTIONS[p])
        else:
            required.append(p)
    required = list(dict.fromkeys(required))
    if not required:
        return True

    if mode == 'all':
        return all(r in codes for r in required)
    return any(r in codes for r in required)


def permission_required(permission, mode='any'):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            if not getattr(g, 'staff_id', None):
                return {'status': 401, 'msg': '请先登录'}
            if not staff_has_permission(permission, mode=mode):
                return {
                    'status': 403,
                    'msg': '无权限执行此操作',
                    'data': {'permission': permission},
                }
            return view_func(*args, **kwargs)
        return wrapper
    return decorator


def login_and_permission(permission, mode='any'):
    from flask_shop.utils.token import login_required

    def decorator(view_func):
        return login_required(permission_required(permission, mode=mode)(view_func))
    return decorator


def staff_permission_payload(user):
    """登录/me 响应用。"""
    if not user or not user.role:
        return {
            'is_super': False,
            'menu_paths': [],
            'actions': [],
        }
    role = user.role
    if _is_super_role(role):
        return {
            'is_super': True,
            'menu_paths': ['*'],
            'actions': list(ALL_ACTION_CODES),
        }
    menu_paths = sorted({m.path for m in (role.menus or []) if m.path})
    codes, _ = get_staff_action_codes(user.id, user.tenant_id)
    return {
        'is_super': False,
        'menu_paths': menu_paths,
        'actions': sorted(codes),
    }
