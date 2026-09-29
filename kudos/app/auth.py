"""Authentication, authorization, CSRF protection and security headers."""

import functools
import hmac
import logging
import secrets

from flask import (
    Blueprint, abort, flash, g, jsonify, redirect, render_template, request,
    session, url_for,
)
from werkzeug.security import check_password_hash

from .db import get_db

bp = Blueprint("auth", __name__)
log = logging.getLogger("kudos")

CSRF_SESSION_KEY = "_csrf_token"


def csrf_token():
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def _csrf_valid():
    expected = session.get(CSRF_SESSION_KEY)
    sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
    return bool(expected and sent and hmac.compare_digest(expected, sent))


def init_app(app):
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def load_user_and_check_csrf():
        user_id = session.get("user_id")
        g.user = None
        if user_id is not None:
            # Re-read every request so role changes/deactivation apply immediately.
            g.user = get_db().execute(
                "SELECT id, email, display_name, department, role FROM users"
                " WHERE id = ? AND is_active = 1",
                (user_id,),
            ).fetchone()
            if g.user is None:
                session.clear()

        if request.method in ("POST", "PUT", "PATCH", "DELETE") and not _csrf_valid():
            log.warning("CSRF check failed on %s %s", request.method, request.path)
            if request.path.startswith("/api/"):
                return jsonify(error={"code": "csrf_failed",
                                      "message": "Your session expired. Refresh the page."}), 403
            abort(403)

    @app.after_request
    def security_headers(resp):
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp


def login_required(view):
    @functools.wraps(view)
    def wrapped(**kwargs):
        if g.user is None:
            if request.path.startswith("/api/"):
                abort(401)
            return redirect(url_for("auth.login", next=request.path))
        return view(**kwargs)

    return wrapped


def admin_required(view):
    @functools.wraps(view)
    @login_required
    def wrapped(**kwargs):
        if g.user["role"] != "admin":
            abort(403)
        return view(**kwargs)

    return wrapped


def _safe_next(target):
    # Only allow local, absolute paths to avoid open redirects.
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("views.dashboard")


@bp.route("/login", methods=("GET", "POST"))
def login():
    if g.user is not None:
        return redirect(url_for("views.dashboard"))
    error = None
    email = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT id, password_hash, is_active FROM users WHERE email = ?", (email,)
        ).fetchone()
        if user and user["is_active"] and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            csrf_token()  # rotate token on login
            return redirect(_safe_next(request.args.get("next")))
        log.warning("Failed login for %s", email)
        error = "Invalid email or password."
    return render_template("login.html", error=error, email=email), (401 if error else 200)


@bp.route("/logout", methods=("POST",))
def logout():
    session.clear()
    flash("You have been signed out.")
    return redirect(url_for("auth.login"))
