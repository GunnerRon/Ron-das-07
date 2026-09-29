import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app.db import SEED_PASSWORD, init_db, seed_db  # noqa: E402

# Seeded ids: 1 admin, 2 alice, 3 ben, 4 chloe, 5 dev, 6 emma
ADMIN, ALICE, BEN, CHLOE = 1, 2, 3, 4


@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.sqlite3")})
    with app.app_context():
        init_db()
        seed_db()
    return app


class Client:
    """Test client wrapper that handles login and CSRF headers."""

    def __init__(self, flask_client):
        self.c = flask_client
        self.token = None

    def _refresh_token(self):
        self.c.get("/login")
        with self.c.session_transaction() as s:
            self.token = s.get("_csrf_token")

    def login(self, email, password=SEED_PASSWORD):
        self._refresh_token()
        resp = self.c.post("/login", data={"email": email, "password": password,
                                           "csrf_token": self.token})
        self._refresh_token()
        return resp

    def get(self, *a, **kw):
        return self.c.get(*a, **kw)

    def post(self, path, json=None, **kw):
        headers = kw.pop("headers", {"X-CSRF-Token": self.token or ""})
        return self.c.post(path, json=json, headers=headers, **kw)

    def delete(self, path, json=None):
        return self.c.delete(path, json=json, headers={"X-CSRF-Token": self.token or ""})


@pytest.fixture
def client(app):
    return Client(app.test_client())


@pytest.fixture
def alice(app):
    c = Client(app.test_client())
    c.login("alice@datacom.example")
    return c


@pytest.fixture
def admin(app):
    c = Client(app.test_client())
    c.login("admin@datacom.example")
    return c
