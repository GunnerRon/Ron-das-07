"""JSON REST API (SPECIFICATION.md section 3.3)."""

from flask import Blueprint, current_app, g, jsonify, request

from . import services
from .auth import admin_required, login_required
from .db import get_db
from .services import KudosError

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.errorhandler(KudosError)
def handle_kudos_error(err):
    body = {"code": err.code, "message": err.message}
    if err.fields:
        body["fields"] = err.fields
    return jsonify(error=body), err.status, err.headers


def _json_body():
    data = request.get_json(silent=True)
    if data is None:
        raise KudosError(400, "bad_request", "Request body must be JSON.")
    return data


@bp.get("/me")
@login_required
def me():
    return jsonify({k: g.user[k] for k in ("id", "email", "display_name", "department", "role")})


@bp.get("/users")
@login_required
def users():
    return jsonify(users=services.list_colleagues(get_db(), g.user["id"], request.args.get("q")))


@bp.get("/kudos")
@login_required
def feed():
    page, per_page = services.parse_pagination(request.args, current_app.config)
    rows, has_more = services.list_feed(get_db(), page, per_page)
    return jsonify(kudos=[services.to_public(r) for r in rows],
                   page=page, per_page=per_page, has_more=has_more)


@bp.post("/kudos")
@login_required
def create():
    row = services.create_kudos(get_db(), current_app.config, g.user["id"], _json_body())
    return jsonify(kudos=services.to_public(row)), 201


@bp.get("/admin/kudos")
@admin_required
def admin_list():
    conn = get_db()
    page, per_page = services.parse_pagination(request.args, current_app.config)
    rows, has_more = services.list_admin(conn, request.args.get("status", "all"), page, per_page)
    return jsonify(kudos=[services.to_admin(conn, r) for r in rows],
                   page=page, per_page=per_page, has_more=has_more)


def _moderate(kudos_id, action):
    conn = get_db()
    payload = request.get_json(silent=True) or {}
    row = services.moderate(conn, g.user["id"], kudos_id, action, payload)
    return jsonify(kudos=services.to_admin(conn, row))


@bp.post("/admin/kudos/<int:kudos_id>/hide")
@admin_required
def hide(kudos_id):
    return _moderate(kudos_id, "hide")


@bp.post("/admin/kudos/<int:kudos_id>/unhide")
@admin_required
def unhide(kudos_id):
    return _moderate(kudos_id, "unhide")


@bp.delete("/admin/kudos/<int:kudos_id>")
@admin_required
def delete(kudos_id):
    return _moderate(kudos_id, "delete")
