# -*- coding: utf-8 -*-
import io
from pathlib import Path

import pytest
from PIL import Image

from flask_shop import db, models
from flask_shop.utils.token import generate_customer_token
from flask_shop.utils.tenant_query import tenant_context


def _image_bytes(image_format='PNG'):
    output = io.BytesIO()
    Image.new('RGB', (2, 2), 'white').save(output, format=image_format)
    return output.getvalue()


def _customer_order(app, seed):
    with app.app_context(), tenant_context(disabled=True):
        c = models.Customer(
            tenant_id=seed["ta"].id,
            phone="13900001111",
            nickname="buyer",
            status=1,
        )
        db.session.add(c)
        db.session.commit()
        order = models.Order.query.get(seed["order_a"].id)
        order.customer_id = c.id
        db.session.commit()
        token = generate_customer_token(c)
        return c.id, order.id, token


def test_customer_can_claim_paid(api, app):
    cid, oid, token = _customer_order(app, api["seed"])
    headers = {"token": token, "X-Tenant-Slug": "test-a"}
    r = api["client"].post(
        f"/api/c/order/{oid}/claim-paid/",
        json={"note": "wei1234"},
        headers=headers,
    )
    body = r.get_json()
    assert r.status_code == 200
    assert body["status"] == 200
    assert body["data"]["buyer_paid_claimed"] == 1
    assert body["data"]["buyer_paid_note"] == "wei1234"
    assert body["data"]["status"] == "pending_pay"


def test_cannot_claim_other_customer_order(api, app):
    _cid, oid, token = _customer_order(app, api["seed"])
    with app.app_context(), tenant_context(disabled=True):
        other = models.Customer(
            tenant_id=api["seed"]["ta"].id,
            phone="13900002222",
            nickname="other",
            status=1,
        )
        db.session.add(other)
        db.session.commit()
        other_token = generate_customer_token(other)
    headers = {"token": other_token, "X-Tenant-Slug": "test-a"}
    r = api["client"].post(
        f"/api/c/order/{oid}/claim-paid/",
        json={"note": "x"},
        headers=headers,
    )
    assert r.get_json()["status"] == 404


def test_admin_can_filter_claimed(api, app):
    _cid, oid, token = _customer_order(app, api["seed"])
    headers = {"token": token, "X-Tenant-Slug": "test-a"}
    api["client"].post(
        f"/api/c/order/{oid}/claim-paid/",
        json={"note": "ok"},
        headers=headers,
    )
    staff = {"token": api["seed"]["token_a"]}
    r = api["client"].get("/orders/?status=pending_pay&claimed=1", headers=staff)
    body = r.get_json()
    assert body["status"] == 200
    nos = [o["order_no"] for o in body["data"]]
    assert "A-ORD-1" in nos
    assert all(int(o.get("buyer_paid_claimed") or 0) == 1 for o in body["data"])


def test_payment_proof_requires_order_access_and_is_not_public(api, app, tmp_path):
    app.config['UPLOAD_FOLDER'] = str(tmp_path / 'public')
    app.config['PAY_PROOF_FOLDER'] = str(tmp_path / 'private')
    _, order_id, customer_token = _customer_order(app, api['seed'])
    customer_headers = {'token': customer_token, 'X-Tenant-Slug': 'test-a'}
    client = api['client']
    image = _image_bytes()
    result = client.post(f'/api/c/order/{order_id}/claim-paid/',
                         data={'file': (io.BytesIO(image), 'proof.png')},
                         headers=customer_headers).get_json()
    path = result['data']['buyer_paid_proof']
    assert path.startswith('private-pay-proof/')
    assert (tmp_path / 'private' / str(api['seed']['id_a']) / path.rsplit('/', 1)[-1]).read_bytes() == image
    assert client.get('/static/upload/' + str(api['seed']['id_a']) + '/pay_proof/' + path.rsplit('/', 1)[-1]).status_code == 404
    customer_response = client.get(f'/api/c/order/{order_id}/pay-proof/', headers=customer_headers)
    assert customer_response.status_code == 200
    assert customer_response.data == image
    assert customer_response.headers['Cache-Control'] == 'private, no-store'
    staff_response = client.get(f'/order/{order_id}/pay-proof/', headers={'token': api['seed']['token_a']})
    assert staff_response.data == image
    assert client.get(f'/order/{order_id}/pay-proof/', headers={'token': api['seed']['token_b']}).status_code == 404
    with tenant_context(disabled=True):
        other = models.Customer(tenant_id=api['seed']['id_a'], phone='13900003333', status=1)
        db.session.add(other)
        db.session.commit()
        other_token = generate_customer_token(other)
    denied = client.get(f'/api/c/order/{order_id}/pay-proof/',
                        headers={'token': other_token, 'X-Tenant-Slug': 'test-a'})
    assert denied.status_code == 404
    assert client.get(f'/api/c/order/{order_id}/pay-proof/',
                      headers={'X-Tenant-Slug': 'test-a'}).get_json()['status'] == 401


@pytest.mark.parametrize('filename,image_format', [
    ('proof.png', 'PNG'), ('proof.jpg', 'JPEG'), ('proof.jpeg', 'JPEG'),
    ('proof.gif', 'GIF'), ('proof.webp', 'WEBP'),
])
def test_payment_proof_accepts_valid_image_formats(api, app, tmp_path, filename, image_format):
    app.config['PAY_PROOF_FOLDER'] = str(tmp_path)
    _, order_id, token = _customer_order(app, api['seed'])
    result = api['client'].post(f'/api/c/order/{order_id}/claim-paid/',
        data={'file': (io.BytesIO(_image_bytes(image_format)), filename)},
        headers={'token': token, 'X-Tenant-Slug': 'test-a'}).get_json()
    assert result['status'] == 200


@pytest.mark.parametrize('filename,content', [
    ('proof.png', b'<html>not an image</html>'),
    ('proof.png', b'\x89PNG\r\n\x1a\ntruncated'),
    ('proof.jpg', _image_bytes('PNG')),
])
def test_payment_proof_rejects_fake_or_mismatched_files(api, app, tmp_path, filename, content):
    app.config['PAY_PROOF_FOLDER'] = str(tmp_path)
    _, order_id, token = _customer_order(app, api['seed'])
    result = api['client'].post(f'/api/c/order/{order_id}/claim-paid/',
        data={'file': (io.BytesIO(content), filename)},
        headers={'token': token, 'X-Tenant-Slug': 'test-a'}).get_json()
    assert result['status'] == 400
    assert not list(tmp_path.rglob('*'))
    with tenant_context(disabled=True):
        order = db.session.get(models.Order, order_id)
        assert not order.buyer_paid_claimed
        assert not order.buyer_paid_proof


def test_payment_proof_rejects_excessive_dimensions(api, app, tmp_path, monkeypatch):
    from flask_shop.utils import pay_proof

    app.config['PAY_PROOF_FOLDER'] = str(tmp_path)
    monkeypatch.setattr(pay_proof, 'MAX_PROOF_PIXELS', 3)
    _, order_id, token = _customer_order(app, api['seed'])
    result = api['client'].post(f'/api/c/order/{order_id}/claim-paid/',
        data={'file': (io.BytesIO(_image_bytes()), 'proof.png')},
        headers={'token': token, 'X-Tenant-Slug': 'test-a'}).get_json()
    assert result['status'] == 400
    assert not list(tmp_path.rglob('*'))


def test_existing_payment_proof_remains_accessible_only_through_authorized_endpoint(api, app, tmp_path):
    app.config['UPLOAD_FOLDER'] = str(tmp_path)
    _, order_id, token = _customer_order(app, api['seed'])
    directory = tmp_path / str(api['seed']['id_a']) / 'pay_proof'
    directory.mkdir(parents=True)
    filename = 'a' * 32 + '.png'
    (directory / filename).write_bytes(b'legacy-proof')
    with tenant_context(disabled=True):
        order = db.session.get(models.Order, order_id)
        order.buyer_paid_proof = f'/static/upload/{order.tenant_id}/pay_proof/{filename}'
        db.session.commit()
    client = api['client']
    assert client.get(order.buyer_paid_proof).status_code == 404
    response = client.get(f'/api/c/order/{order_id}/pay-proof/',
                          headers={'token': token, 'X-Tenant-Slug': 'test-a'})
    assert response.data == b'legacy-proof'


def test_nginx_blocks_public_payment_proof_paths():
    directory = Path(__file__).resolve().parents[2] / 'deploy' / 'nginx' / 'conf.d'
    for name in ('default.conf', 'default.ssl.conf.example', 'shop.conf'):
        text = (directory / name).read_text(encoding='utf-8')
        assert 'location ~* ^/static/upload/[^/]+/pay_proof(?:/|$)' in text


def test_legacy_proof_migration_dry_run_and_execute_are_tenant_scoped(api, app, tmp_path):
    from flask_shop.utils.migrate_pay_proofs import migrate_tenant_proofs

    public = tmp_path / 'public'
    private = tmp_path / 'private'
    app.config['UPLOAD_FOLDER'] = str(public)
    app.config['PAY_PROOF_FOLDER'] = str(private)
    _, order_id, token = _customer_order(app, api['seed'])
    filename = 'a' * 32 + '.png'
    tenant_id = api['seed']['id_a']
    old_path = f'/static/upload/{tenant_id}/pay_proof/{filename}'
    source = public / str(tenant_id) / 'pay_proof' / filename
    source.parent.mkdir(parents=True)
    source.write_bytes(b'legacy-image')
    with tenant_context(disabled=True):
        order = db.session.get(models.Order, order_id)
        order.buyer_paid_proof = old_path
        db.session.commit()
    result = migrate_tenant_proofs(tenant_id)
    assert result == {'checked': 1, 'migrated': 0, 'errors': []}
    assert not private.exists()
    assert db.session.get(models.Order, order_id).buyer_paid_proof == old_path
    assert migrate_tenant_proofs(api['seed']['id_b'], execute=True)['checked'] == 0
    result = migrate_tenant_proofs(tenant_id, execute=True)
    assert result == {'checked': 1, 'migrated': 1, 'errors': []}
    assert source.read_bytes() == b'legacy-image'
    assert (private / str(tenant_id) / filename).read_bytes() == b'legacy-image'
    assert migrate_tenant_proofs(tenant_id, execute=True)['checked'] == 0
    response = api['client'].get(f'/api/c/order/{order_id}/pay-proof/',
        headers={'token': token, 'X-Tenant-Slug': 'test-a'})
    assert response.data == b'legacy-image'


def test_legacy_proof_migration_refuses_conflicting_destination(api, app, tmp_path):
    from flask_shop.utils.migrate_pay_proofs import migrate_tenant_proofs

    public = tmp_path / 'public'
    private = tmp_path / 'private'
    app.config['UPLOAD_FOLDER'] = str(public)
    app.config['PAY_PROOF_FOLDER'] = str(private)
    _, order_id, _ = _customer_order(app, api['seed'])
    tenant_id = api['seed']['id_a']
    filename = 'b' * 32 + '.png'
    source = public / str(tenant_id) / 'pay_proof' / filename
    target = private / str(tenant_id) / filename
    source.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    source.write_bytes(b'original')
    target.write_bytes(b'different')
    with tenant_context(disabled=True):
        order = db.session.get(models.Order, order_id)
        order.buyer_paid_proof = f'/static/upload/{tenant_id}/pay_proof/{filename}'
        db.session.commit()
    result = migrate_tenant_proofs(tenant_id, execute=True)
    assert result['migrated'] == 0 and len(result['errors']) == 1
    assert source.read_bytes() == b'original'
    assert target.read_bytes() == b'different'
    assert db.session.get(models.Order, order_id).buyer_paid_proof.startswith('/static/upload/')
