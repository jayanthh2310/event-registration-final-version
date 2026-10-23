"""
Celestius - Event Registration API
Event: Backend Development Workshop | 20 October 2026 | Capacity: 50

Stack: Python + Flask + SQLite (stdlib sqlite3).

Layout of this file:
  1. Config            4. Validation
  2. Database layer    5. Routes
  3. App factory       6. Error handlers
"""
import hmac
import os
import re
import sqlite3
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, current_app, g, jsonify, request

# ------------------------------------------------------------------ 1. Config
EVENT = {
    "name": "Backend Development Workshop",
    "date": "2026-10-20",
    "capacity": 50,
}
MAX_NAME, MAX_EMAIL, MAX_COLLEGE = 100, 254, 150
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


# ------------------------------------------------------- 2. Database layer
def connect(path):
    # isolation_level=None -> autocommit; we open transactions ourselves with BEGIN IMMEDIATE.
    conn = sqlite3.connect(path, isolation_level=None, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # readers don't block the writer
    return conn


def init_db(path):
    conn = connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS registrations (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
            college       TEXT,
            registered_at TEXT NOT NULL
        )
        """
    )
    conn.close()


def get_db():
    """One connection per request, closed automatically afterwards."""
    if "db" not in g:
        g.db = connect(current_app.config["DB_PATH"])
    return g.db


def row_to_dict(row):
    return {k: row[k] for k in ("id", "name", "email", "college", "registered_at")}


# ------------------------------------------------------------- 3. App factory
def create_app(db_path=None, admin_api_key=None):
    app = Flask(__name__)
    app.json.sort_keys = False
    app.config["DB_PATH"] = db_path or os.environ.get("DB_PATH", "registrations.db")
    # Organizer routes fail closed if no key is configured.
    # Pass admin_api_key explicitly in tests, or set ADMIN_API_KEY in the environment.
    app.config["ADMIN_API_KEY"] = admin_api_key if admin_api_key is not None else os.environ.get("ADMIN_API_KEY")
    init_db(app.config["DB_PATH"])

    @app.teardown_appcontext
    def close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    register_routes(app)
    register_errors(app)
    return app


# ------------------------------------------------------------- 4. Validation
def error(message, status, **extra):
    return jsonify({"error": message, **extra}), status


def validate_registration(data):
    """Returns (clean_values, problems). problems is {} when everything is fine."""
    problems = {}
    name, email, college = data.get("name"), data.get("email"), data.get("college")

    if not isinstance(name, str) or not name.strip():
        problems["name"] = "Name is required."
    elif len(name.strip()) > MAX_NAME:
        problems["name"] = f"Name must be at most {MAX_NAME} characters."

    if not isinstance(email, str) or not email.strip():
        problems["email"] = "Email is required."
    elif len(email.strip()) > MAX_EMAIL or not EMAIL_RE.match(email.strip()):
        problems["email"] = "Email is not valid."

    if college is not None and not isinstance(college, str):
        problems["college"] = "College / department must be a string."
    elif isinstance(college, str) and len(college.strip()) > MAX_COLLEGE:
        problems["college"] = f"College / department must be at most {MAX_COLLEGE} characters."

    if problems:
        return None, problems
    clean = {
        "name": " ".join(name.split()),  # trims and collapses repeated spaces
        "email": email.strip().lower(),
        "college": college.strip() if isinstance(college, str) and college.strip() else None,
    }
    return clean, {}


def admin_required(view):
    """Protect organizer routes; fail closed if the server has no configured key."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        key = current_app.config["ADMIN_API_KEY"]
        if not key:
            return error("Organizer endpoints are disabled until ADMIN_API_KEY is configured.", 503)
        supplied = request.headers.get("X-API-Key", "")
        if not hmac.compare_digest(supplied.encode(), key.encode()):  # constant-time compare
            return error("Unauthorized. Valid X-API-Key header required.", 401)
        return view(*args, **kwargs)

    return wrapper


def parse_int_arg(name, default, minimum, maximum):
    raw = request.args.get(name)
    if raw is None:
        return default, None
    try:
        value = int(raw)
    except ValueError:
        return None, f"'{name}' must be an integer."
    if not minimum <= value <= maximum:
        return None, f"'{name}' must be between {minimum} and {maximum}."
    return value, None


# ------------------------------------------------------------------ 5. Routes
def register_routes(app):
    @app.get("/ui")
    def ui():
        """Optional interactive dashboard (static/ui.html). The API itself needs no frontend."""
        return app.send_static_file("ui.html")

    @app.get("/")
    def index():
        count = get_db().execute("SELECT COUNT(*) FROM registrations").fetchone()[0]
        return jsonify(
            {
                "event": EVENT["name"],
                "date": EVENT["date"],
                "capacity": EVENT["capacity"],
                "registered": count,
                "seats_left": EVENT["capacity"] - count,
                "is_full": count >= EVENT["capacity"],
            }
        )

    @app.post("/register")
    def register():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return error("Request body must be a JSON object.", 400)

        clean, problems = validate_registration(data)
        if problems:
            return error("Invalid or missing information.", 400, details=problems)

        registered_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        db = get_db()

        # BEGIN IMMEDIATE grabs SQLite's write lock *before* we read anything.
        # So "check seats, then insert" is atomic: two simultaneous requests cannot
        # both see 49/50 and both take the last seat.
        db.execute("BEGIN IMMEDIATE")
        try:
            if db.execute("SELECT 1 FROM registrations WHERE email = ?", (clean["email"],)).fetchone():
                db.execute("ROLLBACK")
                return error("This email is already registered.", 409)

            count = db.execute("SELECT COUNT(*) FROM registrations").fetchone()[0]
            if count >= EVENT["capacity"]:
                db.execute("ROLLBACK")
                return error("Event is full.", 409, capacity=EVENT["capacity"])

            cur = db.execute(
                "INSERT INTO registrations (name, email, college, registered_at) VALUES (?, ?, ?, ?)",
                (clean["name"], clean["email"], clean["college"], registered_at),
            )
            db.execute("COMMIT")
        except sqlite3.IntegrityError:  # UNIQUE(email) as a last line of defence
            db.execute("ROLLBACK")
            return error("This email is already registered.", 409)
        except Exception:
            db.execute("ROLLBACK")
            raise

        row = db.execute("SELECT * FROM registrations WHERE id = ?", (cur.lastrowid,)).fetchone()
        resp = jsonify(
            {
                "message": "Registration successful.",
                "registration": row_to_dict(row),
                "seats_left": EVENT["capacity"] - count - 1,
            }
        )
        resp.status_code = 201
        resp.headers["Location"] = f"/registrations/{row['id']}"
        return resp

    @app.get("/registrations")
    @admin_required
    def list_registrations():
        # Optional pagination: ?limit=10&offset=20 (defaults return everyone, max 50 anyway).
        limit, err = parse_int_arg("limit", EVENT["capacity"], 1, 500)
        if err:
            return error(err, 400)
        offset, err = parse_int_arg("offset", 0, 0, 10**9)
        if err:
            return error(err, 400)

        db = get_db()
        total = db.execute("SELECT COUNT(*) FROM registrations").fetchone()[0]
        rows = db.execute(
            "SELECT * FROM registrations ORDER BY id LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()
        return jsonify(
            {
                "total": total,
                "capacity": EVENT["capacity"],
                "limit": limit,
                "offset": offset,
                "registrations": [row_to_dict(r) for r in rows],
            }
        )

    @app.get("/registrations/<int:reg_id>")
    @admin_required
    def get_registration(reg_id):
        row = get_db().execute("SELECT * FROM registrations WHERE id = ?", (reg_id,)).fetchone()
        if row is None:
            return error("Registration not found.", 404)
        return jsonify(row_to_dict(row))

    @app.get("/registrations/email/<path:email>")
    @admin_required
    def get_registration_by_email(email):
        row = get_db().execute(
            "SELECT * FROM registrations WHERE email = ?", (email.strip().lower(),)
        ).fetchone()
        if row is None:
            return error("Registration not found.", 404)
        return jsonify(row_to_dict(row))

    @app.delete("/registrations/<int:reg_id>")
    @admin_required
    def cancel_registration(reg_id):
        """Bonus: cancel a registration, which frees the seat."""
        db = get_db()
        cur = db.execute("DELETE FROM registrations WHERE id = ?", (reg_id,))
        if cur.rowcount == 0:
            return error("Registration not found.", 404)
        return jsonify({"message": "Registration cancelled."})


# ------------------------------------------------------------ 6. Error handlers
def register_errors(app):
    @app.errorhandler(404)
    def not_found(_e):
        return error("Route not found.", 404)

    @app.errorhandler(405)
    def method_not_allowed(_e):
        return error("Method not allowed.", 405)

    @app.errorhandler(sqlite3.OperationalError)
    def db_busy(_e):
        return error("Server is busy, please retry.", 503)

    @app.errorhandler(500)
    def server_error(_e):
        return error("Internal server error.", 500)


app = create_app()

if __name__ == "__main__":
    app.run(debug=False, port=5000)
