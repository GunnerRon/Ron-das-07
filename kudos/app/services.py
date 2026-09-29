"""Business rules for kudos: validation, anti-abuse and moderation.

Every function takes an explicit DB connection and config so it can be unit tested
without an HTTP request. Rules reference SPECIFICATION.md section 2.3.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import timedelta

from .db import iso, utcnow

log = logging.getLogger("kudos")

_CONTROL_CHARS = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")
_MANY_NEWLINES = re.compile(r"\n{3,}")


class KudosError(Exception):
    """A business-rule failure that maps onto an API error envelope."""

    def __init__(self, status, code, message, fields=None, headers=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.fields = fields or {}
        self.headers = headers or {}


def sanitize_message(raw):
    """AC-2.3: normalise newlines, strip control chars, collapse blank lines, trim."""
    if not isinstance(raw, str):
        return ""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS.sub("", text)
    text = _MANY_NEWLINES.sub("\n\n", text)
    return text.strip()


def normalize_for_duplicate(message):
    return " ".join(message.lower().split())


def find_blocked_terms(message, blocked_terms):
    lowered = message.lower()
    return [
        term for term in blocked_terms
        if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", lowered)
    ]


# --------------------------------------------------------------------------- create

def create_kudos(conn, config, sender_id, payload):
    if not isinstance(payload, dict):
        raise KudosError(400, "bad_request", "Expected a JSON object.")

    fields = {}
    recipient_id = payload.get("recipient_id")
    if isinstance(recipient_id, str) and recipient_id.strip().isdigit():
        recipient_id = int(recipient_id)
    if isinstance(recipient_id, bool) or not isinstance(recipient_id, int):
        fields["recipient_id"] = "Please choose a colleague."  # V-1
    elif recipient_id == sender_id:
        fields["recipient_id"] = "You can't give kudos to yourself."  # V-3
    else:
        recipient = conn.execute(
            "SELECT id FROM users WHERE id = ? AND is_active = 1", (recipient_id,)
        ).fetchone()
        if recipient is None:
            fields["recipient_id"] = "That colleague could not be found."  # V-4

    message = sanitize_message(payload.get("message"))
    max_len = config["KUDOS_MESSAGE_MAX"]
    if not message:
        fields["message"] = "Please write a message."  # V-2
    elif len(message) > max_len:
        fields["message"] = f"Message must be {max_len} characters or fewer."

    if fields:
        raise KudosError(400, "validation_error", "Please fix the highlighted fields.", fields)

    # V-5: inappropriate content
    if find_blocked_terms(message, config["KUDOS_BLOCKED_TERMS"]):
        log.warning("Blocked content from user %s", sender_id)
        raise KudosError(
            422, "inappropriate_content",
            "Your message contains language that isn't allowed. Please keep it positive.",
            {"message": "Please remove inappropriate language."},
        )

    now = utcnow()

    # V-7: rate limit
    window = config["KUDOS_RATE_WINDOW_MINUTES"]
    rows = conn.execute(
        "SELECT created_at FROM kudos WHERE sender_id = ? AND created_at > ?"
        " ORDER BY created_at ASC",
        (sender_id, iso(now - timedelta(minutes=window))),
    ).fetchall()
    if len(rows) >= config["KUDOS_RATE_LIMIT"]:
        log.warning("Rate limit hit by user %s", sender_id)
        raise KudosError(
            429, "rate_limited",
            f"You've sent a lot of kudos recently. Please try again later "
            f"(limit {config['KUDOS_RATE_LIMIT']} per {window} minutes).",
            headers={"Retry-After": str(window * 60)},
        )

    # V-6: duplicate submission
    normalized = normalize_for_duplicate(message)
    dup = conn.execute(
        "SELECT id FROM kudos WHERE sender_id = ? AND recipient_id = ?"
        " AND message_normalized = ? AND created_at > ? LIMIT 1",
        (sender_id, recipient_id, normalized,
         iso(now - timedelta(hours=config["KUDOS_DUPLICATE_WINDOW_HOURS"]))),
    ).fetchone()
    if dup:
        log.warning("Duplicate kudos rejected for user %s", sender_id)
        raise KudosError(
            409, "duplicate_kudos",
            "You've already sent this message to this colleague recently.",
        )

    cur = conn.execute(
        "INSERT INTO kudos (sender_id, recipient_id, message, message_normalized, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (sender_id, recipient_id, message, normalized, iso(now)),
    )
    conn.commit()
    log.info("Kudos %s created by user %s for user %s", cur.lastrowid, sender_id, recipient_id)
    return get_kudos(conn, cur.lastrowid)


# --------------------------------------------------------------------------- read

_SELECT = """
    SELECT k.*, s.display_name AS sender_name, r.display_name AS recipient_name,
           m.display_name AS moderator_name
    FROM kudos k
    JOIN users s ON s.id = k.sender_id
    JOIN users r ON r.id = k.recipient_id
    LEFT JOIN users m ON m.id = k.moderated_by
"""


def _status(row):
    if row["is_deleted"]:
        return "deleted"
    return "visible" if row["is_visible"] else "hidden"


def to_public(row):
    return {
        "id": row["id"],
        "message": row["message"],
        "created_at": row["created_at"],
        "sender": {"id": row["sender_id"], "display_name": row["sender_name"]},
        "recipient": {"id": row["recipient_id"], "display_name": row["recipient_name"]},
    }


def to_admin(conn, row):
    data = to_public(row)
    history = conn.execute(
        "SELECT l.action, l.reason, l.created_at, l.admin_id, u.display_name"
        " FROM moderation_log l JOIN users u ON u.id = l.admin_id"
        " WHERE l.kudos_id = ? ORDER BY l.created_at ASC, l.id ASC",
        (row["id"],),
    ).fetchall()
    data.update(
        status=_status(row),
        is_visible=bool(row["is_visible"]),
        is_deleted=bool(row["is_deleted"]),
        moderated_by=(
            {"id": row["moderated_by"], "display_name": row["moderator_name"]}
            if row["moderated_by"] else None
        ),
        moderated_at=row["moderated_at"],
        moderation_reason=row["moderation_reason"],
        history=[
            {"action": h["action"], "reason": h["reason"], "created_at": h["created_at"],
             "admin": {"id": h["admin_id"], "display_name": h["display_name"]}}
            for h in history
        ],
    )
    return data


def get_kudos(conn, kudos_id):
    return conn.execute(_SELECT + " WHERE k.id = ?", (kudos_id,)).fetchone()


def parse_pagination(args, config):
    try:
        page = int(args.get("page", 1))
        per_page = int(args.get("per_page", config["FEED_PER_PAGE_DEFAULT"]))
    except (TypeError, ValueError):
        raise KudosError(400, "validation_error", "page and per_page must be integers.")
    if page < 1 or per_page < 1:
        raise KudosError(400, "validation_error", "page and per_page must be positive.")
    return page, min(per_page, config["FEED_PER_PAGE_MAX"])


def _paginate(conn, where, params, page, per_page):
    rows = conn.execute(
        _SELECT + f" WHERE {where} ORDER BY k.created_at DESC, k.id DESC LIMIT ? OFFSET ?",
        (*params, per_page + 1, (page - 1) * per_page),
    ).fetchall()
    return rows[:per_page], len(rows) > per_page


def list_feed(conn, page, per_page):
    return _paginate(conn, "k.is_visible = 1 AND k.is_deleted = 0", (), page, per_page)


ADMIN_FILTERS = {
    "all": "1 = 1",
    "visible": "k.is_visible = 1 AND k.is_deleted = 0",
    "hidden": "k.is_visible = 0 AND k.is_deleted = 0",
    "deleted": "k.is_deleted = 1",
}


def list_admin(conn, status, page, per_page):
    if status not in ADMIN_FILTERS:
        raise KudosError(400, "validation_error",
                         "status must be one of: " + ", ".join(ADMIN_FILTERS))
    return _paginate(conn, ADMIN_FILTERS[status], (), page, per_page)


# --------------------------------------------------------------------------- moderation

@dataclass
class _Transition:
    is_visible: int
    is_deleted: int
    reason_required: bool
    allowed_from: set = field(default_factory=set)


_TRANSITIONS = {
    "hide": _Transition(0, 0, True, {"visible", "hidden"}),
    "unhide": _Transition(1, 0, False, {"visible", "hidden"}),
    "delete": _Transition(0, 1, True, {"visible", "hidden"}),
}


def moderate(conn, admin_id, kudos_id, action, payload):
    transition = _TRANSITIONS[action]
    row = get_kudos(conn, kudos_id)
    if row is None:
        raise KudosError(404, "not_found", "Kudos not found.")
    if _status(row) not in transition.allowed_from:
        raise KudosError(409, "already_deleted", "This kudos has already been deleted.")

    reason = payload.get("reason") if isinstance(payload, dict) else None
    reason = reason.strip() if isinstance(reason, str) else ""
    if transition.reason_required and not (3 <= len(reason) <= 255):
        raise KudosError(400, "validation_error", "Please give a reason (3-255 characters).",
                         {"reason": "A reason of 3-255 characters is required."})
    if len(reason) > 255:
        raise KudosError(400, "validation_error", "Reason must be 255 characters or fewer.",
                         {"reason": "Reason must be 255 characters or fewer."})

    now = iso(utcnow())
    conn.execute(
        "UPDATE kudos SET is_visible = ?, is_deleted = ?, moderated_by = ?,"
        " moderated_at = ?, moderation_reason = ? WHERE id = ?",
        (transition.is_visible, transition.is_deleted, admin_id, now, reason or None, kudos_id),
    )
    conn.execute(
        "INSERT INTO moderation_log (kudos_id, admin_id, action, reason, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (kudos_id, admin_id, action, reason or None, now),
    )
    conn.commit()
    log.info("Admin %s performed %s on kudos %s", admin_id, action, kudos_id)
    return get_kudos(conn, kudos_id)


# --------------------------------------------------------------------------- users

def list_colleagues(conn, current_user_id, query=""):
    sql = ("SELECT id, display_name, department FROM users"
           " WHERE is_active = 1 AND id <> ?")
    params = [current_user_id]
    query = (query or "").strip()
    if query:
        like = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        sql += " AND (display_name LIKE ? ESCAPE '\\' OR department LIKE ? ESCAPE '\\')"
        params += [like, like]
    sql += " ORDER BY display_name COLLATE NOCASE"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]
