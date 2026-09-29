"""Kudos application factory."""

import logging
import os

from flask import Flask, jsonify, render_template, request

from . import api, auth, db, views
from .config import DEFAULT_SECRET_KEY, Config


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    app.config["DATABASE"] = app.config["DATABASE"] or os.path.join(
        app.instance_path, "kudos.sqlite3"
    )
    if test_config:
        app.config.update(test_config)

    if app.config["ENV_NAME"] == "production" and app.config["SECRET_KEY"] == DEFAULT_SECRET_KEY:
        raise RuntimeError("KUDOS_SECRET_KEY must be set in production")

    os.makedirs(app.instance_path, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    db.init_app(app)
    auth.init_app(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(views.bp)
    app.register_blueprint(api.bp)

    _register_error_handlers(app)
    return app


def _wants_json():
    return request.path.startswith("/api/")


def _register_error_handlers(app):
    log = logging.getLogger("kudos")
    messages = {
        400: ("bad_request", "The request was invalid."),
        401: ("unauthenticated", "Please sign in."),
        403: ("forbidden", "You do not have permission to do that."),
        404: ("not_found", "Not found."),
        405: ("method_not_allowed", "Method not allowed."),
        413: ("payload_too_large", "The request is too large."),
    }

    def handle(code):
        def handler(err):
            key, message = messages[code]
            if _wants_json():
                return jsonify(error={"code": key, "message": message}), code
            return render_template("error.html", code=code, message=message), code

        return handler

    for code in messages:
        app.register_error_handler(code, handle(code))

    @app.errorhandler(Exception)
    def unhandled(err):
        from werkzeug.exceptions import HTTPException

        if isinstance(err, HTTPException):
            return err
        log.exception("Unhandled error on %s %s", request.method, request.path)
        if _wants_json():
            return jsonify(
                error={"code": "internal_error", "message": "Something went wrong."}
            ), 500
        return render_template(
            "error.html", code=500, message="Something went wrong."
        ), 500
