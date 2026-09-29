# Kudos System Specification

| | |
|---|---|
| **Feature** | Kudos: peer-to-peer appreciation for the internal employee portal |
| **Status** | ✅ Approved for implementation (v1.1) |
| **Author** | Graduate Developer (AI Architect role) |
| **Implementation** | [`kudos/`](kudos/) (Flask + SQLite reference implementation) |

---

## 0. Specification History (Spec-Driven Process)

### 0.1 Initial prompt (Step 1)

> Create a feature for our internal web app that allows users to give 'kudos' to their colleagues. A user should be able to select another user from a list, write a short message of appreciation, and submit it. There should also be a public feed on the main dashboard where all recently submitted kudos are visible.

### 0.2 v1.0: AI-generated draft (summary)

The first generated spec covered only the "happy path":

- User stories US-1 to US-4 (select colleague, write message, submit, view feed).
- A `users` table and a `kudos` table (`id`, `sender_id`, `recipient_id`, `message`, `created_at`).
- Endpoints `GET /api/users`, `GET /api/kudos` and `POST /api/kudos`.
- A dashboard page with a form and a feed.

### 0.3 v1.1: Architect review and refinements (Step 2)

Gaps found in the draft and how the spec now handles them:

| # | Gap in v1.0 | Refinement in v1.1 |
|---|---|---|
| R1 | **No content moderation.** Anything posted is public forever. | New user stories **US-5** (admin hides/unhides) and **US-6** (admin deletes) plus an admin moderation page. |
| R2 | Schema cannot represent moderated content. | `kudos` gains `is_visible BOOLEAN DEFAULT TRUE`, `is_deleted`, `moderated_by`, `moderated_at` and `moderation_reason`. A new `moderation_log` table keeps a history of every action. |
| R3 | No roles, so nobody can moderate. | `users.role` (`user` / `admin`) and role-based authorization on `/api/admin/*`. |
| R4 | **Spam** and flooding were not considered. | Rate limit of 10 kudos per sender per rolling hour (HTTP 429). |
| R5 | **Duplicate submissions** (double click, copy-paste spam). | The server rejects the same sender → recipient + normalised message within 24 h (HTTP 409). The client also disables the submit button while a request is in flight. |
| R6 | **Inappropriate content** relies only on admins reacting. | A configurable blocked-terms filter rejects messages up front (HTTP 422). Admin moderation remains the backstop. |
| R7 | Self-kudos and kudos to deactivated users were possible. | Validation rules V-3 and V-4, plus a DB `CHECK` constraint. |
| R8 | No authentication, CSRF or XSS considerations. | Session auth, hashed passwords, CSRF tokens, output escaping, CSP and security headers (§3.5). |
| R9 | The feed was unbounded. | Paginated feed (default 20, max 50) with a covering index. |
| R10 | Hard delete destroys the audit trail. | "Delete" is a soft delete (`is_deleted = 1`). The content is kept for audit and never shown to users again. |

### 0.4 Approval (Step 3)

v1.1 was reviewed against the checklist in `TASK2_INSTRUCTIONS.md` and **approved**. Implementation followed the plan in §4 exactly. Any change to behaviour requires a spec revision first.

---

## 1. Scope

**In scope:** giving kudos, the public dashboard feed, the colleague picker, admin moderation (hide, unhide, delete), anti-spam and anti-abuse controls, and a responsive UI.

**Out of scope (future):** reactions or comments on kudos, email or Teams notifications, SSO integration (the portal's SSO would replace the local login, see §3.5), analytics and leaderboards, and editing a kudos after submission.

**Glossary**

- **Kudos:** a short public message of appreciation from one employee (the *sender*) to another (the *recipient*).
- **Visible:** `is_visible = 1 AND is_deleted = 0`. Only visible kudos appear on the public feed.
- **Hidden:** removed from the feed by an admin. This is reversible.
- **Deleted:** permanently removed from all non-admin views. It cannot be undone in the UI, and the row is retained for audit.

---

## 2. Functional Requirements

### 2.1 User Stories

| ID | Story |
|---|---|
| US-0 | As an employee, I can sign in so that kudos are attributed to me and cannot be forged. |
| US-1 | As a user, I can select another colleague from a searchable list. |
| US-2 | As a user, I can write a message of appreciation (1–500 characters). |
| US-3 | As a user, I can submit the kudos, which is stored in the database and appears on the feed. |
| US-4 | As a user, I can view a feed of recent kudos on the main dashboard, newest first, with pagination. |
| **US-5** | **As an administrator, I can hide an inappropriate kudos (with a reason) so it disappears from the public feed, and unhide it if it was hidden in error.** |
| **US-6** | **As an administrator, I can delete an inappropriate kudos (with a reason) so it is permanently removed from all user-facing views while an audit record is retained.** |
| **US-7** | **As an administrator, I can see all kudos, including hidden and deleted ones, filtered by status, together with who moderated them, when and why.** |
| US-8 | As a user on a phone, tablet or desktop, I can use every feature comfortably. |

### 2.2 Acceptance Criteria

**US-0: Authentication**
- AC-0.1 Unauthenticated requests to pages redirect to `/login`. Unauthenticated API calls return `401`.
- AC-0.2 Wrong credentials show a generic "Invalid email or password" message, without revealing which part was wrong.
- AC-0.3 Deactivated users cannot sign in.
- AC-0.4 Sign-out clears the session. It is a POST protected by CSRF.

**US-1: Select colleague**
- AC-1.1 The list contains all *active* users except the current user, sorted by display name.
- AC-1.2 The list can be filtered by typing part of a name or department.
- AC-1.3 Each option shows the display name and department.

**US-2: Write message**
- AC-2.1 The message is trimmed. It must contain 1 to 500 characters after trimming.
- AC-2.2 A live character counter shows the remaining characters and warns below 50.
- AC-2.3 Control characters (other than newline) are stripped. Runs of 3 or more newlines collapse to 2.

**US-3: Submit**
- AC-3.1 A valid submission returns `201` and the new kudos. It appears at the top of the feed without a full page reload.
- AC-3.2 Validation failures return `400` or `422` with field-level messages that are shown inline next to the relevant field.
- AC-3.3 The submit button is disabled while the request is in flight.
- AC-3.4 The sender is always the authenticated user. Any `sender_id` in the request body is ignored.

**US-4: Feed**
- AC-4.1 The feed shows only *visible* kudos, newest first.
- AC-4.2 Each item shows the sender, recipient, message and relative time (with an absolute timestamp on hover).
- AC-4.3 The feed is paginated at 20 per page by default (max 50), with a "Load more" control.
- AC-4.4 Messages render as plain text. HTML in a message is displayed literally and never executed.

**US-5 / US-6 / US-7: Moderation**
- AC-5.1 Only users with `role = 'admin'` can access `/admin` and `/api/admin/*`. Other users get `403`.
- AC-5.2 Hide and delete require a reason of 3–255 characters. Unhide takes an optional reason.
- AC-5.3 Hiding sets `is_visible = 0`, `moderated_by`, `moderated_at` and `moderation_reason`, and writes a `moderation_log` row. The kudos disappears from the feed immediately.
- AC-5.4 Unhiding sets `is_visible = 1`, updates the moderation fields and writes a log row.
- AC-6.1 Deleting sets `is_deleted = 1` and `is_visible = 0`, updates the moderation fields and writes a log row. A deleted kudos cannot be unhidden (`409`) or deleted again (`409`).
- AC-6.2 Moderating a non-existent kudos returns `404`.
- AC-7.1 The admin view lists kudos filtered by `all | visible | hidden | deleted`, showing their moderation metadata and history.

### 2.3 Validation and Abuse-Prevention Rules (Edge Cases)

| ID | Rule | Response |
|---|---|---|
| V-1 | `recipient_id` is required and must be an integer | `400 validation_error` |
| V-2 | The message must be 1–500 characters after sanitising | `400 validation_error` |
| V-3 | The sender cannot be the recipient | `400 validation_error` |
| V-4 | The recipient must exist and be active | `400 validation_error` |
| V-5 | **Blocked terms:** a message containing a configured blocked term (whole word, case-insensitive) is rejected | `422 inappropriate_content` |
| V-6 | **Duplicate:** the same sender, recipient and normalised message (lower-case, whitespace collapsed) within 24 h is rejected | `409 duplicate_kudos` |
| V-7 | **Rate limit / spam:** a sender can submit at most 10 kudos per rolling 60 minutes | `429 rate_limited` with a `Retry-After` header |
| V-8 | The request body must be JSON and at most 16 KB | `400` / `413` |
| V-9 | A missing or invalid CSRF token on a state-changing request is rejected | `403 csrf_failed` |

The blocked-terms list, rate limit and duplicate window are configuration values (`KUDOS_BLOCKED_TERMS`, `KUDOS_RATE_LIMIT`, `KUDOS_RATE_WINDOW_MINUTES`, `KUDOS_DUPLICATE_WINDOW_HOURS`).

### 2.4 Non-Functional Requirements

- **Responsive:** mobile-first CSS. There is a single-column layout under 768 px and a two-column layout (form | feed) above it. Touch targets are at least 44 px.
- **Accessible:** form controls have labels, errors are linked via `aria-describedby`, the feed is a live region announcing new kudos, and colour contrast is AA or better.
- **Performance:** feed queries are served by an index and p95 is under 100 ms for 100k rows.
- **Auditability:** every moderation action is recorded with the actor, time, action and reason.

---

## 3. Technical Design

### 3.1 Architecture

```
Browser (HTML + vanilla JS)
   │  fetch() JSON, same-origin session cookie, X-CSRF-Token header
   ▼
Flask app  ──  views.py  (server-rendered pages: /login, /, /admin)
           ──  api.py    (JSON REST API under /api)
           ──  auth.py   (session login, role decorators, CSRF)
           ──  services.py (business rules: validation, spam, moderation)
           ──  db.py     (SQLite access, schema, seed data)
   ▼
SQLite (portable to PostgreSQL: standard SQL, no SQLite-only features in queries)
```

The layers are kept separate so that the business rules in `services.py` are pure and unit-testable. HTTP concerns stay in `api.py` and `views.py`.

### 3.2 Database Schema

```sql
CREATE TABLE users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    email          TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    display_name   TEXT    NOT NULL,
    department     TEXT    NOT NULL DEFAULT '',
    password_hash  TEXT    NOT NULL,
    role           TEXT    NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    is_active      INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE kudos (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id          INTEGER NOT NULL REFERENCES users(id),
    recipient_id       INTEGER NOT NULL REFERENCES users(id),
    message            TEXT    NOT NULL CHECK (length(message) BETWEEN 1 AND 500),
    message_normalized TEXT    NOT NULL,              -- for duplicate detection (V-6)
    created_at         TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    -- Moderation fields (architect refinement R2)
    is_visible         INTEGER NOT NULL DEFAULT 1 CHECK (is_visible IN (0, 1)),
    is_deleted         INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    moderated_by       INTEGER REFERENCES users(id),
    moderated_at       TEXT,
    moderation_reason  TEXT,
    CHECK (sender_id <> recipient_id)
);

-- Feed query: WHERE is_visible = 1 AND is_deleted = 0 ORDER BY created_at DESC
CREATE INDEX idx_kudos_feed      ON kudos (is_visible, is_deleted, created_at DESC);
-- Rate-limit and duplicate checks
CREATE INDEX idx_kudos_sender    ON kudos (sender_id, created_at);
CREATE INDEX idx_kudos_recipient ON kudos (recipient_id, created_at);

CREATE TABLE moderation_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kudos_id    INTEGER NOT NULL REFERENCES kudos(id),
    admin_id    INTEGER NOT NULL REFERENCES users(id),
    action      TEXT    NOT NULL CHECK (action IN ('hide', 'unhide', 'delete')),
    reason      TEXT,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX idx_modlog_kudos ON moderation_log (kudos_id, created_at);
```

**Relationships:** `users 1─* kudos` (as sender), `users 1─* kudos` (as recipient), `users 1─* kudos` (as moderator), `kudos 1─* moderation_log`, and `users 1─* moderation_log` (as admin).

All timestamps are UTC ISO-8601 strings. Foreign keys are enforced (`PRAGMA foreign_keys = ON`).

### 3.3 API Endpoints

All responses are JSON. Errors use a single envelope:

```json
{ "error": { "code": "validation_error", "message": "Please fix the highlighted fields.", "fields": { "message": "Message is required." } } }
```

State-changing requests (`POST`, `DELETE`) must send the `X-CSRF-Token` header. The token is embedded in each page as `<meta name="csrf-token">`.

| Method & Path | Auth | Request | Success | Errors |
|---|---|---|---|---|
| `GET /api/me` | user | – | `200 {id, email, display_name, department, role}` | 401 |
| `GET /api/users?q=` | user | `q` optional filter on name or department | `200 {users: [{id, display_name, department}]}` for active users, excluding the caller | 401 |
| `GET /api/kudos?page=1&per_page=20` | user | pagination (per_page ≤ 50) | `200 {kudos: [Kudos], page, per_page, has_more}` for visible kudos only | 400, 401 |
| `POST /api/kudos` | user | `{recipient_id: int, message: str}` | `201 {kudos: Kudos}` | 400, 401, 403, 409, 413, 422, 429 |
| `GET /api/admin/kudos?status=all&page=1` | admin | `status ∈ all, visible, hidden, deleted` | `200 {kudos: [AdminKudos], page, per_page, has_more}` | 400, 401, 403 |
| `POST /api/admin/kudos/<id>/hide` | admin | `{reason: str(3..255)}` | `200 {kudos: AdminKudos}` | 400, 401, 403, 404, 409 |
| `POST /api/admin/kudos/<id>/unhide` | admin | `{reason?: str}` | `200 {kudos: AdminKudos}` | 401, 403, 404, 409 |
| `DELETE /api/admin/kudos/<id>` | admin | `{reason: str(3..255)}` | `200 {kudos: AdminKudos}` | 400, 401, 403, 404, 409 |

**Kudos:** `{id, message, created_at, sender: {id, display_name}, recipient: {id, display_name}}`

**AdminKudos:** Kudos plus `{status: "visible"|"hidden"|"deleted", is_visible, is_deleted, moderated_by: {id, display_name}|null, moderated_at, moderation_reason, history: [{action, reason, created_at, admin: {id, display_name}}]}`

Hiding an already-hidden kudos is idempotent (`200`). It updates the reason and logs the action. Moderating a deleted kudos returns `409 already_deleted`.

**Page routes:** `GET/POST /login`, `POST /logout`, `GET /` (dashboard), `GET /admin` (admin only), and `GET /healthz`.

### 3.4 Frontend Components

```
base.html (header: brand, user name, [Admin] link if admin, Sign out)
├── login.html
│   └── LoginForm
├── dashboard.html
│   ├── GiveKudosCard
│   │   ├── RecipientPicker (search input + <select> of colleagues, fed by GET /api/users)
│   │   ├── MessageField (textarea + CharCounter)
│   │   ├── FormErrors (inline per-field + banner)
│   │   └── SubmitButton (disabled while in flight)
│   └── KudosFeed (aria-live list)
│       ├── KudosCard × n (sender → recipient, message, relative time)
│       └── LoadMoreButton (GET /api/kudos?page=n+1)
└── admin.html
    ├── StatusFilterTabs (all | visible | hidden | deleted)
    └── ModerationTable / cards
        └── ModerationRow (message, people, status badge, history, [Hide|Unhide] [Delete])
```

**Interactions:** a successful submit prepends the new card to `KudosFeed` and resets the form. A server error maps `error.fields` onto the matching inputs. Admin actions prompt for a reason, call the API, and re-render the row in place. All user content is inserted with `textContent`, never `innerHTML`.

### 3.5 Security Considerations

- **Authentication:** server-side session cookie (`HttpOnly`, `SameSite=Lax`, and `Secure` in production). Passwords are hashed with PBKDF2 via Werkzeug. The local login is an adapter: in production the portal's SSO (OIDC/Azure AD) populates the same session keys.
- **Authorization:** `@login_required` and `@admin_required` decorators run on every route. The role is re-read from the DB on each request, so demotion or deactivation takes effect immediately.
- **CSRF:** a per-session random token is required on all state-changing requests (form field or `X-CSRF-Token` header) and compared in constant time.
- **XSS:** Jinja auto-escaping, `textContent` in JS, and a strict `Content-Security-Policy` (`default-src 'self'`, no inline script).
- **Other headers:** `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` and `Referrer-Policy: same-origin`.
- **Injection:** only parameterised SQL.
- **Mass assignment:** `sender_id` always comes from the session (AC-3.4).
- **Least disclosure:** the user list exposes only id, name and department, never email or role.
- **Request size:** `MAX_CONTENT_LENGTH = 16 KB`.

### 3.6 Performance Considerations

- Offset pagination with `LIMIT per_page + 1` to compute `has_more` without a `COUNT(*)`. It can move to keyset pagination (`created_at < ?`) if the feed grows very large.
- The feed query is a single `JOIN` (kudos + sender + recipient) using `idx_kudos_feed`, which avoids N+1 queries.
- Rate-limit and duplicate checks use `idx_kudos_sender`.
- The static assets are small with no build step. Feed responses send `Cache-Control: no-store` because they are per-user authenticated data. A short shared cache (for example 10 s) is a future option behind a reverse proxy.

### 3.7 Error Handling and Logging

- Every error returns the JSON envelope from §3.3 for `/api/*`, or a friendly HTML page for pages. Unhandled exceptions return a generic `500 internal_error` and never leak stack traces.
- Logging uses Python `logging` with the logger name `kudos`. Levels:
  - `INFO`: kudos created (ids only, no message body), and every moderation action (admin id, kudos id, action).
  - `WARNING`: rejected submissions (rate limit, duplicate, blocked content), failed logins (email only) and CSRF failures.
  - `ERROR`: unhandled exceptions, logged with the stack trace.

---

## 4. Implementation Plan

| # | Task | Depends on | Output |
|---|---|---|---|
| T1 | Project scaffold, config, app factory, `requirements.txt` | – | `kudos/app/__init__.py`, `config.py` |
| T2 | Schema, DB helpers, seed data (6 users incl. 1 admin, sample kudos) | T1 | `schema.sql`, `db.py`, `flask --app app init-db` |
| T3 | Auth: login/logout, session, `login_required`/`admin_required`, CSRF, security headers | T2 | `auth.py` |
| T4 | Domain services: validation (V-1…V-7), create kudos, feed query, moderation (hide/unhide/delete + log) | T2 | `services.py` |
| T5 | JSON API + error envelope | T3, T4 | `api.py` |
| T6 | Pages + responsive CSS + JS (dashboard, feed, picker, admin) | T5 | `templates/`, `static/` |
| T7 | Automated tests | T3–T6 | `tests/` |
| T8 | README with run/test instructions; final spec committed | T7 | `kudos/README.md`, `SPECIFICATION.md` |

### 4.1 Testing Strategy

- **Unit (services):** message sanitisation, each validation rule V-1 to V-7, the moderation state machine (visible ⇄ hidden → deleted, where deleted is terminal) and log writing.
- **Integration (Flask test client, temp SQLite DB per test):** authentication redirects and 401s, CSRF enforcement, the full submit → feed flow, hidden and deleted kudos disappearing from the feed, 403 for non-admins on admin endpoints, pagination, XSS payloads returned literally, and security headers.
- **Manual:** responsive layout checked at 375 px, 768 px and 1280 px, and keyboard-only navigation.
- **CI gate:** `pytest` must pass before merge.

### 4.2 Deployment Considerations

- Runs behind the portal's reverse proxy under WSGI (`gunicorn "app:create_app()"`).
- `SECRET_KEY` and `DATABASE` come from environment variables. The app refuses to start in production mode with the default secret key.
- SQLite suits a pilot. The SQL is portable to PostgreSQL for production, and migrations would move to Alembic.
- The rate limiter is DB-backed, so it works across multiple workers without shared memory.
- `/healthz` is available for load-balancer health checks.
- Swapping the local login for portal SSO only requires changing `auth.login`.

---

## 5. Requirements Traceability

| Checklist item | Where |
|---|---|
| User authentication and authorization | US-0, AC-5.1, §3.5, `auth.py` |
| User selection from a list | US-1, `GET /api/users`, RecipientPicker |
| Kudos creation and submission | US-2, US-3, `POST /api/kudos` |
| Public feed | US-4, `GET /api/kudos`, KudosFeed |
| Content moderation | US-5 to US-7, §3.2 moderation fields, `/api/admin/*` |
| Input validation and error handling | §2.3, §3.7 |
| Responsive design | §2.4, `static/styles.css` |
| Schema, API, components | §3.2 to §3.4 |
| Security and performance | §3.5, §3.6 |
| Tasks, dependencies, testing, deployment | §4 |
