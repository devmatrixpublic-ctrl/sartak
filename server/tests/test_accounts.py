import pytest
from sqlalchemy import text

from app.accounts.identity import PhoneVerifier, phone_hash, phone_verifier_dependency
from app.core.errors import ApiError
from app.core.settings import Settings
from app.db.models import Account, Device
from app.main import app

PHONE = "+919876543210"
A = {"Authorization": "Bearer phone-a"}
B = {"Authorization": "Bearer phone-b"}


class FakeVerifier:
    """Stands in for Firebase: the token is the phone number it 'proves', or 'bad' for a token that fails."""

    def verify(self, id_token: str) -> str:
        if id_token == "bad":
            raise ApiError(401, "invalid_id_token", "The sign-in could not be verified.")
        return id_token


@pytest.fixture(autouse=True)
def _fake_phone_auth():
    app.dependency_overrides[phone_verifier_dependency] = lambda: FakeVerifier()
    yield
    app.dependency_overrides.pop(phone_verifier_dependency, None)


def test_a_new_number_creates_an_account_with_the_name(client, db):
    r = client.post("/account", json={"id_token": PHONE, "name": "Ved"}, headers=A)
    assert r.status_code == 200
    assert r.json() == {"name": "Ved", "created": True}
    assert client.get("/account", headers=A).json()["name"] == "Ved"


def test_the_number_itself_is_never_stored(client, db, db_engine):
    client.post("/account", json={"id_token": PHONE, "name": "Ved"}, headers=A)
    with db_engine.connect() as c:
        dump = " ".join(str(v) for row in c.execute(text("select * from accounts")) for v in row)
    assert PHONE not in dump and "9876543210" not in dump
    assert len(db.query(Account).one().phone_hash) == 64


def test_the_same_number_on_a_second_phone_joins_the_same_account(client, db):
    client.post("/account", json={"id_token": PHONE, "name": "Ved"}, headers=A)
    r = client.post("/account", json={"id_token": PHONE}, headers=B)
    assert r.json() == {"name": "Ved", "created": False}
    assert db.query(Account).count() == 1
    assert {d.account_id for d in db.query(Device).all()} == {db.query(Account).one().id}


def test_signing_in_again_with_a_name_changes_it(client):
    client.post("/account", json={"id_token": PHONE, "name": "Ved"}, headers=A)
    assert client.post("/account", json={"id_token": PHONE, "name": "Ved R"}, headers=A).json()["name"] == "Ved R"


def test_a_name_is_optional_and_can_be_set_later(client):
    r = client.post("/account", json={"id_token": PHONE}, headers=A)
    assert r.json()["name"] is None
    assert client.patch("/account", json={"name": "  Priya "}, headers=A).json()["name"] == "Priya"


def test_a_token_that_does_not_verify_is_refused_and_creates_nothing(client, db):
    r = client.post("/account", json={"id_token": "bad", "name": "X"}, headers=A)
    assert r.status_code == 401 and r.json()["code"] == "invalid_id_token"
    assert db.query(Account).count() == 0


def test_a_phone_with_no_account_gets_404(client):
    assert client.get("/account", headers=A).status_code == 404
    assert client.patch("/account", json={"name": "x"}, headers=A).status_code == 404


def test_unknown_fields_and_oversize_names_are_rejected(client):
    assert client.post("/account", json={"id_token": PHONE, "phone": PHONE}, headers=A).status_code == 422
    assert client.post("/account", json={"id_token": PHONE, "name": "x" * 61}, headers=A).status_code == 422


def test_delete_my_data_removes_the_account_only_with_its_last_phone(client, db):
    client.post("/account", json={"id_token": PHONE}, headers=A)
    client.post("/account", json={"id_token": PHONE}, headers=B)
    assert client.delete("/device", headers=A).status_code == 204
    assert db.query(Account).count() == 1, "another phone still uses it"
    db.expire_all()
    assert client.delete("/device", headers=B).status_code == 204
    db.expire_all()
    assert db.query(Account).count() == 0


def test_the_hash_depends_on_a_server_secret():
    a = Settings(jwt_secret="x" * 40, phone_pepper="one")
    b = Settings(jwt_secret="x" * 40, phone_pepper="two")
    assert phone_hash(PHONE, a) != phone_hash(PHONE, b)
    assert phone_hash(PHONE, a) == phone_hash(PHONE, a)


def test_the_dev_token_only_works_on_a_dev_server():
    dev = PhoneVerifier(Settings(env="dev"))
    assert dev.verify("dev:" + PHONE) == PHONE
    with pytest.raises(ApiError) as bad:
        dev.verify("dev:12345")
    assert bad.value.status_code == 401
    prod = PhoneVerifier(Settings(env="production", jwt_secret="y" * 40))
    with pytest.raises(ApiError) as e:
        prod.verify("dev:" + PHONE)
    assert e.value.status_code == 503, "no Firebase configured and the dev shortcut is off"


def test_signing_out_unlinks_the_phone_and_drops_an_account_nobody_uses(client, db):
    client.post("/account", json={"id_token": PHONE, "name": "Ved"}, headers=A)
    assert client.delete("/account", headers=A).status_code == 204
    assert client.get("/account", headers=A).status_code == 404
    db.expire_all()
    assert db.query(Account).count() == 0
    assert client.delete("/account", headers=A).status_code == 204, "signing out twice is harmless"


def test_signing_out_keeps_the_account_for_its_other_phone(client, db):
    client.post("/account", json={"id_token": PHONE, "name": "Ved"}, headers=A)
    client.post("/account", json={"id_token": PHONE}, headers=B)
    client.delete("/account", headers=A)
    db.expire_all()
    assert db.query(Account).count() == 1
    assert client.get("/account", headers=B).json()["name"] == "Ved"
