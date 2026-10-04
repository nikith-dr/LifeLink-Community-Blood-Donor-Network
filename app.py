import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "lifelink.db")

app = Flask(__name__)
app.secret_key = os.environ.get(
    "LIFELINK_SECRET_KEY",
    "change-this-secret-key"
)

BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
ROLES = ["donor", "requester", "volunteer"]

# Only administrator
ADMIN_EMAIL = "nikithdr@gmail.com"
ADMIN_PASSWORD = "niki@2007"


# -------------------- DATABASE --------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)

    if db is not None:
        db.close()


def init_db():
    db = get_db()

    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        phone TEXT NOT NULL,
        role TEXT NOT NULL,
        blood_group TEXT,
        city TEXT NOT NULL,
        available INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS blood_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        requester_id INTEGER NOT NULL,
        blood_group TEXT NOT NULL,
        units INTEGER NOT NULL,
        hospital TEXT NOT NULL,
        city TEXT NOT NULL,
        urgency TEXT NOT NULL,
        contact TEXT NOT NULL,
        notes TEXT,
        status TEXT DEFAULT 'Active',
        created_at TEXT NOT NULL,
        FOREIGN KEY (requester_id)
            REFERENCES users(id)
            ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS volunteer_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        requester_id INTEGER NOT NULL,
        assistance TEXT NOT NULL,
        location TEXT NOT NULL,
        urgency TEXT NOT NULL,
        contact TEXT NOT NULL,
        notes TEXT,
        status TEXT DEFAULT 'Open',
        created_at TEXT NOT NULL,
        FOREIGN KEY (requester_id)
            REFERENCES users(id)
            ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS responses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER NOT NULL,
        donor_id INTEGER NOT NULL,
        response TEXT NOT NULL DEFAULT 'I Can Help',
        created_at TEXT NOT NULL,
        UNIQUE(request_id, donor_id),
        FOREIGN KEY (request_id)
            REFERENCES blood_requests(id)
            ON DELETE CASCADE,
        FOREIGN KEY (donor_id)
            REFERENCES users(id)
            ON DELETE CASCADE
    );
    """)

    # Remove admin role from every other account.
    db.execute(
        """
        UPDATE users
        SET role='volunteer'
        WHERE role='admin' AND email != ?
        """,
        (ADMIN_EMAIL,)
    )

    # Create or reset the owner's admin account.
    existing = db.execute(
        "SELECT id FROM users WHERE email=?",
        (ADMIN_EMAIL,)
    ).fetchone()

    if not existing:
        db.execute(
            """
            INSERT INTO users
            (name, email, password, phone, role,
             blood_group, city, available, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Nikith D R",
                ADMIN_EMAIL,
                generate_password_hash(ADMIN_PASSWORD),
                "9999999999",
                "admin",
                None,
                "Bengaluru",
                1,
                datetime.now().isoformat(timespec="seconds")
            )
        )

    else:
        db.execute(
            """
            UPDATE users
            SET name=?, password=?, role=?
            WHERE email=?
            """,
            (
                "Nikith D R",
                generate_password_hash(ADMIN_PASSWORD),
                "admin",
                ADMIN_EMAIL
            )
        )

    db.commit()


@app.before_request
def before_request():
    init_db()


@app.context_processor
def inject_globals():
    return {
        "blood_groups": BLOOD_GROUPS
    }


# -------------------- HOME --------------------

@app.route("/")
def index():
    db = get_db()

    blood = db.execute(
        """
        SELECT br.*, u.name AS requester_name
        FROM blood_requests br
        JOIN users u ON u.id=br.requester_id
        WHERE br.status='Active'
        ORDER BY br.id DESC
        LIMIT 8
        """
    ).fetchall()

    volunteers = db.execute(
        """
        SELECT vr.*, u.name AS requester_name
        FROM volunteer_requests vr
        JOIN users u ON u.id=vr.requester_id
        WHERE vr.status='Open'
        ORDER BY vr.id DESC
        LIMIT 8
        """
    ).fetchall()

    return render_template(
        "index.html",
        blood=blood,
        volunteers=volunteers
    )


# -------------------- USER REGISTRATION --------------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        phone = request.form["phone"].strip()
        role = request.form["role"]
        blood_group = request.form.get("blood_group") or None
        city = request.form["city"].strip()

        if role not in ROLES:
            flash("Invalid role.", "danger")
            return redirect(url_for("register"))

        # Admin email cannot be registered by normal users.
        if email == ADMIN_EMAIL:
            flash(
                "This email is reserved for the administrator.",
                "danger"
            )
            return redirect(url_for("register"))

        if role == "donor" and blood_group not in BLOOD_GROUPS:
            flash(
                "Donors must select a valid blood group.",
                "danger"
            )
            return redirect(url_for("register"))

        if len(password) < 6:
            flash(
                "Password must contain at least 6 characters.",
                "danger"
            )
            return redirect(url_for("register"))

        db = get_db()

        try:
            db.execute(
                """
                INSERT INTO users
                (name, email, password, phone, role,
                 blood_group, city, available, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    email,
                    generate_password_hash(password),
                    phone,
                    role,
                    blood_group,
                    city,
                    1,
                    datetime.now().isoformat(timespec="seconds")
                )
            )

            db.commit()

            flash(
                "Registration successful. Please login.",
                "success"
            )

            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash(
                "That email is already registered.",
                "danger"
            )

    return render_template("register.html")


# -------------------- NORMAL USER LOGIN --------------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"].strip().lower()
        password = request.form["password"]

        # Admin must use the separate Admin Login.
        if email == ADMIN_EMAIL:
            flash(
                "Please use the Admin Login option.",
                "warning"
            )
            return redirect(url_for("admin_login"))

        user = get_db().execute(
            "SELECT * FROM users WHERE email=?",
            (email,)
        ).fetchone()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session.clear()

            session["user_id"] = user["id"]
            session["role"] = user["role"]
            session["name"] = user["name"]

            flash(
                "Welcome to LifeLink.",
                "success"
            )

            return redirect(url_for("dashboard"))

        flash(
            "Invalid email or password.",
            "danger"
        )

    return render_template("login.html")


# -------------------- SEPARATE ADMIN LOGIN --------------------

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        email = request.form["email"].strip().lower()
        password = request.form["password"]

        # Only the administrator email is accepted here.
        if email != ADMIN_EMAIL:
            flash(
                "Only the system administrator can use this login.",
                "danger"
            )
            return redirect(url_for("admin_login"))

        user = get_db().execute(
            """
            SELECT * FROM users
            WHERE email=? AND role='admin'
            """,
            (email,)
        ).fetchone()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session.clear()

            session["user_id"] = user["id"]
            session["role"] = "admin"
            session["name"] = user["name"]

            flash(
                "Admin login successful.",
                "success"
            )

            return redirect(url_for("admin"))

        flash(
            "Invalid admin email or password.",
            "danger"
        )

    return render_template("admin_login.html")


# -------------------- LOGOUT --------------------

@app.route("/logout")
def logout():

    session.clear()

    flash(
        "You have been logged out.",
        "info"
    )

    return redirect(url_for("index"))


# -------------------- LOGIN CHECK --------------------

def login
