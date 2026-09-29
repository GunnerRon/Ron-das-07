from conftest import ALICE, BEN


def send(c, recipient=BEN, message="Thanks for the help!"):
    return c.post("/api/kudos", json={"recipient_id": recipient, "message": message})


def test_users_list_excludes_self_and_hides_emails(alice):
    users = alice.get("/api/users").get_json()["users"]
    ids = [u["id"] for u in users]
    assert ALICE not in ids and BEN in ids
    assert set(users[0]) == {"id", "display_name", "department"}
    names = [u["display_name"] for u in users]
    assert names == sorted(names, key=str.lower)


def test_users_filter(alice):
    users = alice.get("/api/users?q=design").get_json()["users"]
    assert [u["display_name"] for u in users] == ["Chloe Singh"]
    assert alice.get("/api/users?q=%25").get_json()["users"] == []  # LIKE wildcard escaped


def test_users_list_excludes_inactive(app, alice):
    from app.db import get_db
    with app.app_context():
        get_db().execute("UPDATE users SET is_active = 0 WHERE id = ?", (BEN,))
        get_db().commit()
    ids = [u["id"] for u in alice.get("/api/users").get_json()["users"]]
    assert BEN not in ids


def test_create_and_appears_first_in_feed(alice):
    resp = send(alice, message="  You rock, Ben!  ")
    assert resp.status_code == 201
    k = resp.get_json()["kudos"]
    assert k["message"] == "You rock, Ben!"
    assert k["sender"]["id"] == ALICE and k["recipient"]["id"] == BEN
    feed = alice.get("/api/kudos").get_json()["kudos"]
    assert feed[0]["id"] == k["id"]


def test_sender_id_in_body_is_ignored(alice):
    resp = alice.post("/api/kudos", json={"recipient_id": BEN, "message": "Hi", "sender_id": 5})
    assert resp.get_json()["kudos"]["sender"]["id"] == ALICE


def test_string_recipient_id_accepted(alice):
    assert send(alice, recipient=str(BEN)).status_code == 201


def test_validation_errors(alice):
    resp = alice.post("/api/kudos", json={"message": ""})
    body = resp.get_json()["error"]
    assert resp.status_code == 400 and body["code"] == "validation_error"
    assert set(body["fields"]) == {"recipient_id", "message"}


def test_whitespace_only_message_rejected(alice):
    resp = send(alice, message=" \n\t ")
    assert resp.get_json()["error"]["fields"]["message"]


def test_message_length_limit(alice):
    assert send(alice, message="x" * 500).status_code == 201
    resp = send(alice, message="y" * 501)
    assert resp.status_code == 400
    assert "500" in resp.get_json()["error"]["fields"]["message"]


def test_cannot_send_to_self(alice):
    resp = send(alice, recipient=ALICE)
    assert resp.status_code == 400
    assert "yourself" in resp.get_json()["error"]["fields"]["recipient_id"]


def test_unknown_recipient(alice):
    assert send(alice, recipient=9999).status_code == 400


def test_bool_recipient_rejected(alice):
    assert send(alice, recipient=True).status_code == 400


def test_blocked_terms_rejected(alice):
    resp = send(alice, message="You are an IDIOT")
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "inappropriate_content"


def test_duplicate_rejected(alice):
    assert send(alice, message="Great work today").status_code == 201
    resp = send(alice, message="great   WORK today ")
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "duplicate_kudos"
    # Same message to a different colleague is fine
    assert send(alice, recipient=4, message="Great work today").status_code == 201


def test_rate_limit(app, alice):
    app.config["KUDOS_RATE_LIMIT"] = 3
    for i in range(3):
        assert send(alice, message=f"Thanks #{i}").status_code == 201
    resp = send(alice, message="One too many")
    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "3600"


def test_non_json_body(alice):
    resp = alice.c.post("/api/kudos", data="nope", headers={"X-CSRF-Token": alice.token})
    assert resp.status_code == 400


def test_payload_too_large(alice):
    resp = send(alice, message="x" * 20000)
    assert resp.status_code == 413
    assert resp.get_json()["error"]["code"] == "payload_too_large"


def test_xss_payload_is_returned_literally(alice):
    payload = "<script>alert(1)</script>"
    send(alice, message=payload)
    assert alice.get("/api/kudos").get_json()["kudos"][0]["message"] == payload
    assert b"<script>alert" not in alice.get("/").data


def test_feed_pagination(alice, app):
    app.config["KUDOS_RATE_LIMIT"] = 100
    for i in range(5):
        send(alice, message=f"Message {i}")
    # 3 seeded + 5 new = 8
    p1 = alice.get("/api/kudos?per_page=5").get_json()
    p2 = alice.get("/api/kudos?per_page=5&page=2").get_json()
    assert len(p1["kudos"]) == 5 and p1["has_more"] is True
    assert len(p2["kudos"]) == 3 and p2["has_more"] is False
    assert not {k["id"] for k in p1["kudos"]} & {k["id"] for k in p2["kudos"]}


def test_feed_per_page_capped_and_validated(alice):
    assert alice.get("/api/kudos?per_page=1000").get_json()["per_page"] == 50
    assert alice.get("/api/kudos?page=abc").status_code == 400
    assert alice.get("/api/kudos?page=0").status_code == 400


def test_dashboard_renders(alice):
    resp = alice.get("/")
    assert resp.status_code == 200
    assert b"Give kudos" in resp.data and b"Recent kudos" in resp.data
    assert b"Moderation" not in resp.data  # admin link hidden for users
