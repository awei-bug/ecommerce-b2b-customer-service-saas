# -*- coding: utf-8 -*-
"""后台菜单默认数据（单一来源）。

`flask_shop/tenant_onboarding.py`（正式租户开通）和
`scripts/seeds/seed_shop.py`（演示店初始化）都需要同一份菜单表数据。
此前两处各存了一份逐字相同的 MENU_L1/MENU_L2，改动一处就会漂移，
故统一到这里。

注意：商家后台左侧导航是 `vue_shop/src/views/HomeView.vue` 里硬编码的，
本表只驱动「权限管理 → 菜单列表 / 角色菜单」这两个底层页面，
不影响普通商家可见的导航（见 README「商家后台已收敛为 7 个一级入口」）。
"""
from __future__ import annotations

# (菜单名, 路径标识)
MENU_L1: list[tuple[str, str]] = [
    ("用户管理", "users"),
    ("权限管理", "rights"),
    ("商品管理", "goods"),
    ("订单管理", "orders"),
    ("数据统计", "reports"),
    ("客服中心", "service"),
    ("店铺设置", "shop"),
]

# (菜单名, 路径标识, 父级菜单名)
MENU_L2: list[tuple[str, str, str]] = [
    ("用户列表", "user_list", "用户管理"),
    ("角色列表", "role_list", "权限管理"),
    ("权限分配", "author_list", "权限管理"),
    ("动作权限", "role_actions", "权限管理"),
    ("商品列表", "product_list", "商品管理"),
    ("添加商品", "add_product", "商品管理"),
    ("分类参数", "attribute_list", "商品管理"),
    ("商品分类", "group_list", "商品管理"),
    ("运费模板", "freight", "商品管理"),
    ("订单列表", "order_list", "订单管理"),
    ("数据报表", "data_list", "数据统计"),
    ("客服工作台", "customer_service", "客服中心"),
    ("店铺设置", "shop_settings", "店铺设置"),
]
