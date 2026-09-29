"""SQLite access, schema initialisation and seed data."""

import sqlite3
from datetime import datetime, timedelta, timezone

import click
from flask import current_app, g
from werkzeug.security import generate_password_hash


def utcnow():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db():
    conn = get_db()
    with current_app.open_resource("schema.sql") as f:
        conn.executescript(f.read().decode("utf8"))


SEED_USERS = [
    # email, display_name, department, role
    ("admin@datacom.example", "Aroha Admin", "People & Culture", "admin"),
    ("alice@datacom.example", "Alice Nguyen", "Engineering", "user"),
    ("ben@datacom.example", "Ben Taylor", "Engineering", "user"),
    ("chloe@datacom.example", "Chloe Singh", "Design", "user"),
    ("dev@datacom.example", "Dev Patel", "Cloud Services", "user"),
    ("emma@datacom.example", "Emma Wilson", "Sales", "user"),
]
SEED_PASSWORD = "password123"


def seed_db():
    conn = get_db()
    pw = generate_password_hash(SEED_PASSWORD)
    for email, name, dept, role in SEED_USERS:
        conn.execute(
            "INSERT INTO users (email, display_name, department, password_hash, role)"
            " VALUES (?, ?, ?, ?, ?)",
            (email, name, dept, pw, role),
        )
    now = utcnow()
    samples = [
        (2, 3, "Thanks for pairing with me on the flaky pipeline - you saved my week!", 180),
        (4, 2, "Your design review feedback was spot on. The new layout is so much clearer.", 120),
        (5, 6, "Huge effort landing the client demo environment on time.", 45),
    ]
    for sender, recipient, msg, mins_ago in samples:
        conn.execute(
            "INSERT INTO kudos (sender_id, recipient_id, message, message_normalized, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (sender, recipient, msg, " ".join(msg.lower().split()),
             iso(now - timedelta(minutes=mins_ago))),
        )
    conn.commit()


@click.command("init-db")
@click.option("--no-seed", is_flag=True, help="Create empty tables without demo data.")
def init_db_command(no_seed):
    """Drop and recreate all tables (and seed demo data)."""
    init_db()
    if not no_seed:
        seed_db()
        click.echo(f"Seeded demo users (password: {SEED_PASSWORD}).")
    click.echo("Initialised the database.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
