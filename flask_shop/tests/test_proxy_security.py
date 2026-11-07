from pathlib import Path

import pytest
from flask import Flask, request

from flask_shop import configure_proxy
from flask_shop.utils.auth_security import _client_ip
from flask_shop.utils.rate_limit import _buckets, _client_key, rate_limit


ROOT = Path(__file__).resolve().parents[2]


def make_app(hops):
    app = Flask(__name__)
    app.config['TRUST_PROXY_HOPS'] = hops
    configure_proxy(app)

    @app.get('/client')
    @rate_limit(max_calls=2, per_seconds=60, prefix=f'proxy_test_{hops}')
    def client():
        return {'remote': request.remote_addr, 'auth': _client_ip(), 'key': _client_key('check')}

    return app


def test_direct_requests_cannot_spoof_rate_limit_or_auth_ip():
    _buckets.clear()
    app = make_app(0)
    client = app.test_client()
    for spoof in ('198.51.100.1', '198.51.100.2'):
        response = client.get('/client', headers={'X-Forwarded-For': spoof},
                              environ_base={'REMOTE_ADDR': '203.0.113.9'})
        assert response.get_json() == {'remote': '203.0.113.9', 'auth': '203.0.113.9', 'key': 'check:203.0.113.9'}
    blocked = client.get('/client', headers={'X-Forwarded-For': '198.51.100.3'},
                         environ_base={'REMOTE_ADDR': '203.0.113.9'})
    assert blocked.status_code == 429
    _buckets.clear()


def test_configured_proxy_uses_only_the_last_forwarded_address():
    _buckets.clear()
    app = make_app(1)
    response = app.test_client().get('/client', headers={
        'X-Forwarded-For': '198.51.100.99, 203.0.113.8',
    }, environ_base={'REMOTE_ADDR': '172.20.0.2'})
    assert response.get_json() == {'remote': '203.0.113.8', 'auth': '203.0.113.8', 'key': 'check:203.0.113.8'}
    _buckets.clear()


def test_unknown_proxy_hop_count_fails_closed():
    with pytest.raises(RuntimeError, match='TRUST_PROXY_HOPS'):
        make_app(2)


def test_rate_limit_caps_buckets_and_reclaims_expired_entries(monkeypatch):
    from flask_shop.utils import rate_limit as limiter

    limiter._buckets.clear()
    monkeypatch.setattr(limiter, '_MAX_BUCKETS', 2)
    monkeypatch.setattr(limiter, '_last_cleanup', 0.0)
    clock = [100.0]
    monkeypatch.setattr(limiter.time, 'monotonic', lambda: clock[0])
    client = make_app(0).test_client()
    def request_from(address):
        return client.get('/client', environ_base={'REMOTE_ADDR': address})

    try:
        assert request_from('192.0.2.1').status_code == 200
        assert request_from('192.0.2.2').status_code == 200
        assert request_from('192.0.2.3').status_code == 503
        assert request_from('192.0.2.1').status_code == 200
        assert request_from('192.0.2.1').status_code == 429
        assert len(limiter._buckets) == 2
        clock[0] += 61
        assert request_from('192.0.2.3').status_code == 200
        assert len(limiter._buckets) == 1
    finally:
        limiter._buckets.clear()


def test_nginx_replaces_instead_of_appending_untrusted_forwarded_header():
    directory = ROOT / 'deploy' / 'nginx' / 'conf.d'
    for name in ('default.conf', 'shop.conf', 'default.ssl.conf.example'):
        text = (directory / name).read_text(encoding='utf-8')
        assert 'proxy_set_header X-Forwarded-For $remote_addr;' in text
        assert '$proxy_add_x_forwarded_for' not in text


def test_compose_loads_one_site_and_checks_api_health():
    compose = (ROOT / 'deploy' / 'docker-compose.yml').read_text(encoding='utf-8')
    assert '${NGINX_SITE_CONFIG:-./nginx/conf.d/default.conf}:/etc/nginx/conf.d/default.conf:ro' in compose
    assert './nginx/conf.d:/etc/nginx/conf.d:ro' not in compose
    directory = ROOT / 'deploy' / 'nginx' / 'conf.d'
    for name in ('default.conf', 'default.ssl.conf.example'):
        config = (directory / name).read_text(encoding='utf-8')
        health = config.split('location = /healthz', 1)[1].split('}', 1)[0]
        assert 'proxy_pass http://api:5000/health/;' in health
        assert 'return 200' not in health
        assert 'image/jpeg jpg jpeg;' in config
        assert 'image/png png;' in config


def test_production_metrics_are_not_public(monkeypatch, tmp_path):
    from config import TestConfig
    from flask_shop import create_app
    from flask_shop import config_map

    monkeypatch.setattr(TestConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{(tmp_path / "metrics.sqlite").as_posix()}')
    monkeypatch.setitem(config_map, 'product', TestConfig)
    app = create_app('product', initialize_schema=False, start_background=False)
    response = app.test_client().get('/metrics/')
    assert response.status_code == 404
    assert response.get_json() == {'status': 404, 'msg': 'not found'}
