import os
import subprocess
import sys
from pathlib import Path

import pytest

from flask_shop import db, models
from flask_shop.utils.tenant_query import tenant_context


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'flask_shop'


def run_seed(script, database_uri, *args, config='develop'):
    env = os.environ.copy()
    env.update(FLASK_CONFIG=config, DATABASE_URL=str(database_uri), PYTHONIOENCODING='utf-8',
               PYTHONPATH=str(BACKEND))
    return subprocess.run([sys.executable, str(script), *args], cwd=BACKEND, env=env,
                          capture_output=True, text=True, encoding='utf-8', timeout=30)


@pytest.mark.parametrize('script', [
    BACKEND / 'scripts/seeds/seed_shop.py',
    BACKEND / 'scripts/seeds/seed_tenants.py',
    BACKEND / 'scripts/seeds/seed_rbac_roles.py',
    BACKEND / 'scripts/seeds/reset_demo_passwords.py',
    BACKEND / 'scripts/seeds/seed_business_demo.py',
    BACKEND / 'scripts/seeds/apply_v1_defaults.py',
    BACKEND / 'scripts/seeds/seed_coupons.py',
    BACKEND / 'scripts/seeds/seed_freight.py',
    BACKEND / 'scripts/seeds/seed_product_images.py',
    ROOT / 'deploy/docker_seed.py',
])
def test_demo_seed_rejects_production_before_connecting(script, tmp_path):
    database = tmp_path / 'untouched.sqlite'
    result = run_seed(script, f'sqlite:///{database.as_posix()}', config='product')
    assert result.returncode != 0
    assert '拒绝在生产配置' in result.stderr + result.stdout
    assert not database.exists()


@pytest.mark.parametrize('name', ['seed_shop.py', 'seed_tenants.py'])
def test_demo_seed_rejects_full_reset_before_database_connection(name, tmp_path, monkeypatch):
    database = tmp_path / 'untouched.sqlite'
    monkeypatch.setenv('ALLOW_DB_RESET', '1')
    result = run_seed(BACKEND / 'scripts/seeds' / name, f'sqlite:///{database.as_posix()}', '--reset')
    assert result.returncode != 0
    assert '已禁用整库重置' in result.stderr + result.stdout
    assert not database.exists()


def test_docker_seed_rejects_flask_env_production_before_defaulting_to_sample(tmp_path):
    database = tmp_path / 'untouched.sqlite'
    env = os.environ.copy()
    env.pop('FLASK_CONFIG', None)
    env.update(FLASK_ENV='production', DATABASE_URL=f'sqlite:///{database.as_posix()}',
               PYTHONIOENCODING='utf-8', PYTHONPATH=str(BACKEND))
    result = subprocess.run([sys.executable, str(ROOT / 'deploy/docker_seed.py')], cwd=BACKEND, env=env,
                            capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode != 0
    assert '拒绝在生产配置' in result.stderr + result.stdout
    assert not database.exists()


def test_reset_passwords_only_touches_demo_tenants(app):
    with tenant_context(disabled=True):
        live_user = models.User.query.filter_by(name='admin_a').first()
        live_user.password = 'live-password-strong'
        demo = models.Tenant(name='演示', slug='demo-password-test', status=1, data_mode='demo')
        db.session.add(demo)
        db.session.flush()
        demo_user = models.User(tenant_id=demo.id, name='admin_a')
        demo_user.password = 'demo-password-old'
        db.session.add(demo_user)
        db.session.commit()
        live_id, demo_id = live_user.id, demo_user.id
        result = run_seed(BACKEND / 'scripts/seeds/reset_demo_passwords.py', app.config['SQLALCHEMY_DATABASE_URI'])
        assert result.returncode == 0, result.stderr
        db.session.expire_all()
        assert db.session.get(models.User, live_id).check_password('live-password-strong')
        assert db.session.get(models.User, demo_id).check_password('123456')


def test_role_seed_does_not_create_users_for_live_tenant(app):
    result = run_seed(BACKEND / 'scripts/seeds/seed_rbac_roles.py', app.config['SQLALCHEMY_DATABASE_URI'], '--with-users')
    assert result.returncode == 0, result.stderr
    with tenant_context(disabled=True):
        db.session.expire_all()
        assert not models.User.query.filter(models.User.name.in_(['clerk', 'warehouse', 'ops', 'cs'])).first()


def test_demo_shop_seed_refuses_live_shop_named_demo(app):
    with tenant_context(disabled=True):
        tenant = models.Tenant(name='正式店铺', slug='demo', status=1, data_mode='live')
        db.session.add(tenant)
        db.session.commit()
        tenant_id = tenant.id
        result = run_seed(BACKEND / 'scripts/seeds/seed_shop.py', app.config['SQLALCHEMY_DATABASE_URI'])
        assert result.returncode != 0
        assert '拒绝修改非演示模式' in result.stderr
        db.session.expire_all()
        assert db.session.get(models.Tenant, tenant_id).data_mode == 'live'


def test_demo_shop_seed_preserves_existing_admin_password(app):
    with tenant_context(disabled=True):
        tenant = models.Tenant(name='演示店铺', slug='demo', status=1, data_mode='demo')
        db.session.add(tenant)
        db.session.flush()
        admin = models.User(tenant_id=tenant.id, name='admin')
        admin.password = 'previous-password'
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id
        result = run_seed(BACKEND / 'scripts/seeds/seed_shop.py', app.config['SQLALCHEMY_DATABASE_URI'])
        assert result.returncode == 0, result.stderr
        db.session.expire_all()
        assert db.session.get(models.User, admin_id).check_password('previous-password')


@pytest.mark.parametrize('name', ['seed_business_demo.py', 'apply_v1_defaults.py', 'seed_coupons.py'])
def test_other_demo_seeds_refuse_live_demo_tenant(app, name):
    with tenant_context(disabled=True):
        tenant = models.Tenant(name='正式店铺', slug='demo', status=1, data_mode='live')
        db.session.add(tenant)
        db.session.commit()
        result = run_seed(BACKEND / 'scripts/seeds' / name, app.config['SQLALCHEMY_DATABASE_URI'])
        assert result.returncode != 0
        assert '拒绝修改非演示模式' in result.stderr + result.stdout


def test_demo_image_seed_does_not_touch_live_products(app):
    result = run_seed(BACKEND / 'scripts/seeds/seed_product_images.py', app.config['SQLALCHEMY_DATABASE_URI'])
    assert result.returncode == 1
    assert 'no products' in result.stdout
    with tenant_context(disabled=True):
        db.session.expire_all()
        assert all(not product.big_img for product in models.Product.query.all())


def test_demo_freight_seed_does_not_add_freight_to_live_tenant(app):
    with tenant_context(disabled=True):
        tenant = models.Tenant(name='正式店铺', slug='live-no-freight', status=1, data_mode='live')
        db.session.add(tenant)
        db.session.commit()
        tenant_id = tenant.id
        result = run_seed(BACKEND / 'scripts/seeds/seed_freight.py', app.config['SQLALCHEMY_DATABASE_URI'])
        assert result.returncode == 0, result.stderr
        db.session.expire_all()
        assert not models.FreightTemplate.query.filter_by(tenant_id=tenant_id).first()
