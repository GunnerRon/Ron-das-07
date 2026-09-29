from conftest import BEN


def create(alice, message="Moderate me"):
    return alice.post("/api/kudos", json={"recipient_id": BEN, "message": message}).get_json()["kudos"]["id"]


def feed_ids(c):
    return [k["id"] for k in c.get("/api/kudos").get_json()["kudos"]]


def test_non_admin_forbidden(alice):
    kid = create(alice)
    assert alice.get("/admin").status_code == 403
    assert alice.get("/api/admin/kudos").status_code == 403
    assert alice.post(f"/api/admin/kudos/{kid}/hide", json={"reason": "nope"}).status_code == 403
    assert alice.delete(f"/api/admin/kudos/{kid}", json={"reason": "nope"}).status_code == 403


def test_admin_page_renders(admin):
    resp = admin.get("/admin")
    assert resp.status_code == 200 and b"Kudos moderation" in resp.data


def test_hide_removes_from_feed_and_records_metadata(alice, admin):
    kid = create(alice)
    resp = admin.post(f"/api/admin/kudos/{kid}/hide", json={"reason": "Off-topic"})
    assert resp.status_code == 200
    k = resp.get_json()["kudos"]
    assert k["status"] == "hidden" and k["is_visible"] is False
    assert k["moderated_by"]["display_name"] == "Aroha Admin"
    assert k["moderation_reason"] == "Off-topic" and k["moderated_at"]
    assert k["history"][0]["action"] == "hide"
    assert kid not in feed_ids(alice)


def test_unhide_restores(alice, admin):
    kid = create(alice)
    admin.post(f"/api/admin/kudos/{kid}/hide", json={"reason": "Checking"})
    resp = admin.post(f"/api/admin/kudos/{kid}/unhide", json={})
    assert resp.get_json()["kudos"]["status"] == "visible"
    assert kid in feed_ids(alice)
    assert [h["action"] for h in resp.get_json()["kudos"]["history"]] == ["hide", "unhide"]


def test_reason_required(alice, admin):
    kid = create(alice)
    for body in ({}, {"reason": ""}, {"reason": "ab"}, {"reason": "x" * 256}):
        resp = admin.post(f"/api/admin/kudos/{kid}/hide", json=body)
        assert resp.status_code == 400, body
        assert "reason" in resp.get_json()["error"]["fields"]
    assert admin.delete(f"/api/admin/kudos/{kid}", json={}).status_code == 400


def test_delete_is_soft_and_terminal(app, alice, admin):
    kid = create(alice)
    resp = admin.delete(f"/api/admin/kudos/{kid}", json={"reason": "Harassment"})
    k = resp.get_json()["kudos"]
    assert k["status"] == "deleted" and k["is_deleted"] is True
    assert kid not in feed_ids(alice)
    # Row retained for audit
    from app.db import get_db
    with app.app_context():
        assert get_db().execute("SELECT 1 FROM kudos WHERE id = ?", (kid,)).fetchone()
    # Terminal state
    assert admin.post(f"/api/admin/kudos/{kid}/unhide", json={}).status_code == 409
    assert admin.post(f"/api/admin/kudos/{kid}/hide", json={"reason": "again"}).status_code == 409
    assert admin.delete(f"/api/admin/kudos/{kid}", json={"reason": "again"}).status_code == 409


def test_moderate_missing_kudos(admin):
    assert admin.post("/api/admin/kudos/9999/hide", json={"reason": "gone"}).status_code == 404


def test_admin_filters(alice, admin):
    a, b, c = create(alice, "One"), create(alice, "Two"), create(alice, "Three")
    admin.post(f"/api/admin/kudos/{b}/hide", json={"reason": "hide it"})
    admin.delete(f"/api/admin/kudos/{c}", json={"reason": "delete it"})

    def ids(status):
        return {k["id"] for k in admin.get(f"/api/admin/kudos?status={status}").get_json()["kudos"]}

    assert {a, b, c} <= ids("all")
    assert a in ids("visible") and b not in ids("visible") and c not in ids("visible")
    assert ids("hidden") == {b}
    assert ids("deleted") == {c}
    assert admin.get("/api/admin/kudos?status=bogus").status_code == 400


def test_hidden_kudos_still_counts_for_duplicate_check(alice, admin):
    kid = create(alice, "Same thing")
    admin.post(f"/api/admin/kudos/{kid}/hide", json={"reason": "spam"})
    resp = alice.post("/api/kudos", json={"recipient_id": BEN, "message": "Same thing"})
    assert resp.status_code == 409


def test_demoted_admin_loses_access_immediately(app, admin):
    from app.db import get_db
    with app.app_context():
        get_db().execute("UPDATE users SET role = 'user' WHERE id = 1")
        get_db().commit()
    assert admin.get("/api/admin/kudos").status_code == 403
