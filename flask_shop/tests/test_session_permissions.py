"""The current merchant session must expose only server-derived permissions."""
from flask_shop import db, models


def test_session_requires_valid_merchant_identity_and_matching_tenant(api):
    client, seed = api['client'], api['seed']
    assert client.get('/user/me/').get_json()['status'] == 401
    assert client.get('/user/me/', headers={'token': 'invalid'}).get_json()['status'] == 401
    mismatch = client.get('/user/me/', headers={'token': seed['token_a'], 'X-Tenant-Id': str(seed['id_b'])}).get_json()
    assert mismatch['status'] == 403


def test_session_permissions_follow_current_role_not_token_claims(api, app):
    client, seed = api['client'], api['seed']
    with app.app_context():
        user = models.User.query.filter_by(name='admin_a', tenant_id=seed['id_a']).first()
        user.role.name = '商品查看员'
        user.role.perm_codes = '["product:read"]'
        db.session.commit()
    response = client.get('/user/me/', headers={'token': seed['token_a']}).get_json()
    assert response['status'] == 200
    assert response['data']['tenant']['id'] == seed['id_a']
    assert response['data']['permissions']['actions'] == ['product:read']
    assert response['data']['permissions']['is_super'] is False
    with app.app_context():
        user = models.User.query.filter_by(name='admin_a', tenant_id=seed['id_a']).first()
        user.role.perm_codes = '[]'
        db.session.commit()
    # The shared test fixture keeps an outer application context alive between
    # requests; expire that session to model separate real request contexts.
    db.session.expire_all()
    response = client.get('/user/me/', headers={'token': seed['token_a']}).get_json()
    assert response['data']['permissions']['actions'] == []
