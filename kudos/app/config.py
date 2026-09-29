"""Configuration defaults. Override with environment variables prefixed KUDOS_."""

import os

DEFAULT_SECRET_KEY = "dev-only-change-me"


class Config:
    SECRET_KEY = os.environ.get("KUDOS_SECRET_KEY", DEFAULT_SECRET_KEY)
    DATABASE = os.environ.get("KUDOS_DATABASE")  # defaults to instance/kudos.sqlite3
    ENV_NAME = os.environ.get("KUDOS_ENV", "development")

    MAX_CONTENT_LENGTH = 16 * 1024  # V-8
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = ENV_NAME == "production"

    # Business rules (SPECIFICATION.md section 2.3)
    KUDOS_MESSAGE_MAX = 500
    KUDOS_RATE_LIMIT = int(os.environ.get("KUDOS_RATE_LIMIT", 10))
    KUDOS_RATE_WINDOW_MINUTES = int(os.environ.get("KUDOS_RATE_WINDOW_MINUTES", 60))
    KUDOS_DUPLICATE_WINDOW_HOURS = int(os.environ.get("KUDOS_DUPLICATE_WINDOW_HOURS", 24))
    KUDOS_BLOCKED_TERMS = [
        t.strip().lower()
        for t in os.environ.get(
            "KUDOS_BLOCKED_TERMS", "idiot,stupid,moron,loser,dumb,useless,hate"
        ).split(",")
        if t.strip()
    ]
    FEED_PER_PAGE_DEFAULT = 20
    FEED_PER_PAGE_MAX = 50
