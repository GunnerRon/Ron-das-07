from conftest import ALICE


def test_pages_redirect_when_logged_out(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_api_returns_401_when_logged_out(client):
    resp = client.get("/api/kudos")
    assert resp.status_code == 401
    assert resp.get_json()["error"]["code"] == "unauthenticated"


def test_login_success_and_me(alice):
    me = alice.get("/api/me").get_json()
    assert me["id"] == ALICE and me["role"] == "user"


def test_login_failure_is_generic(client):
    resp = client.login("alice@datacom.example", "wrong")
    assert resp.status_code == 401
    assert b"Invalid email or password" in resp.data
    resp = client.login("nobody@datacom.example", "wrong")
    assert b"Invalid email or password" in resp.data


def test_inactive_user_cannot_login(app, client):
    from app.db import get_db
    with app.app_context():
        get_db().execute("UPDATE users SET is_active = 0 WHERE id = ?", (ALICE,))
        get_db().commit()
    resp = client.login("alice@datacom.example")
    assert resp.status_code == 401


def test_deactivation_takes_effect_on_existing_session(app, alice):
    from app.db import get_db
    with app.app_context():
        get_db().execute("UPDATE users SET is_active = 0 WHERE id = ?", (ALICE,))
        get_db().commit()
    assert alice.get("/api/me").status_code == 401


def test_open_redirect_blocked(client):
    client._refresh_token()
    resp = client.c.post("/login?next=//evil.example", data={
        "email": "alice@datacom.example", "password": "password123", "csrf_token": client.token})
    assert resp.headers["Location"] == "/"


def test_csrf_required_for_api_posts(alice):
    resp = alice.post("/api/kudos", json={"recipient_id": 3, "message": "hi"}, headers={})
    assert resp.status_code == 403
    assert resp.get_json()["error"]["code"] == "csrf_failed"


def test_csrf_required_for_login_form(client):
    resp = client.c.post("/login", data={"email": "alice@datacom.example", "password": "password123"})
    assert resp.status_code == 403


def test_logout(alice):
    resp = alice.c.post("/logout", data={"csrf_token": alice.token})
    assert resp.status_code == 302
    assert alice.get("/api/me").status_code == 401


def test_security_headers(alice):
    resp = alice.get("/")
    assert "default-src 'self'" in resp.headers["Content-Security-Policy"]
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


def test_healthz(client):
    assert client.get("/healthz").get_json() == {"status": "ok"}
