"""Server-rendered pages. Data is loaded client-side from the JSON API."""

from flask import Blueprint, current_app, render_template

from .auth import admin_required, login_required

bp = Blueprint("views", __name__)


@bp.get("/")
@login_required
def dashboard():
    return render_template("dashboard.html", max_len=current_app.config["KUDOS_MESSAGE_MAX"])


@bp.get("/admin")
@admin_required
def admin():
    return render_template("admin.html")


@bp.get("/healthz")
def healthz():
    return {"status": "ok"}
