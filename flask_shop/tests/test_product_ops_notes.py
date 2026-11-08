"""运营提示后台接口：只按当前租户返回，且不暴露无绑定或空提示的知识记录。"""
import json

from flask_shop import db, models


def test_ops_notes_endpoint_is_tenant_scoped(api, app):
    client, seed = api['client'], api['seed']
    with app.app_context():
        db.session.add_all([
            models.ProductKnowledge(
                tenant_id=seed['id_a'], external_id='note-a',
                product_id=seed['product_a'].id, title='A',
                knowledge_json=json.dumps({'ops_note': '补货提示 A'}),
            ),
            models.ProductKnowledge(
                tenant_id=seed['id_b'], external_id='note-b',
                product_id=seed['product_b'].id, title='B',
                knowledge_json=json.dumps({'ops_note': '补货提示 B'}),
            ),
            models.ProductKnowledge(
                tenant_id=seed['id_a'], external_id='note-unbound',
                product_id=None, title='未绑定商品',
                knowledge_json=json.dumps({'ops_note': '不应该出现'}),
            ),
            models.ProductKnowledge(
                tenant_id=seed['id_a'], external_id='note-empty',
                product_id=seed['product_a'].id, title='空提示',
                knowledge_json=json.dumps({'ops_note': None}),
            ),
        ])
        db.session.commit()

    response = client.get('/products/ops-notes/', headers={'token': seed['token_a']})
    assert response.status_code == 200
    body = response.get_json()
    assert body['status'] == 200
    assert body['data'] == {str(seed['product_a'].id): '补货提示 A'}


def test_ops_notes_endpoint_requires_login(api):
    # 项目现有的 login_required 以业务状态码表达未登录，HTTP 层仍是 200。
    response = api['client'].get('/products/ops-notes/')
    assert response.get_json().get('status') == 401
