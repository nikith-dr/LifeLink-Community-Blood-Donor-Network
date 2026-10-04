from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, g, render_template_string
)
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "lifelink-secret-key-2026"
)

DATABASE = "lifelink.db"

# ============================================================
# ADMIN DETAILS
# ============================================================

ADMIN_EMAIL = "nikithdr@gmail.com"
ADMIN_PASSWORD = "niki@2007"
ADMIN_NAME = "Nikith D R"


# ============================================================
# DATABASE
# ============================================================

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)

    if db is not None:
        db.close()


def init_db():
    db = get_db()

    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            phone TEXT,
            blood_group TEXT,
            location TEXT,
            role TEXT DEFAULT 'donor',
            available INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS blood_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            patient_name TEXT NOT NULL,
            blood_group TEXT NOT NULL,
            units INTEGER DEFAULT 1,
            hospital TEXT,
            location TEXT,
            urgency TEXT DEFAULT 'Normal',
            description TEXT,
            status TEXT DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS volunteer_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT NOT NULL,
            phone TEXT,
            location TEXT,
            help_type TEXT,
            description TEXT,
            status TEXT DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER,
            donor_id INTEGER,
            response_type TEXT DEFAULT 'Blood',
            message TEXT,
            status TEXT DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(request_id) REFERENCES blood_requests(id),
            FOREIGN KEY(donor_id) REFERENCES users(id)
        )
    """)

    # --------------------------------------------------------
    # CREATE / RESET ONLY THE OFFICIAL ADMIN
    # --------------------------------------------------------

    admin = db.execute(
        "SELECT id FROM users WHERE email=?",
        (ADMIN_EMAIL,)
    ).fetchone()

    if admin:
        db.execute("""
            UPDATE users
            SET name=?,
                password=?,
                role='admin',
                available=1
            WHERE email=?
        """, (
            ADMIN_NAME,
            generate_password_hash(ADMIN_PASSWORD),
            ADMIN_EMAIL
        ))
    else:
        db.execute("""
            INSERT INTO users
            (name, email, password, phone, blood_group, location, role, available)
            VALUES (?, ?, ?, ?, ?, ?, 'admin', 1)
        """, (
            ADMIN_NAME,
            ADMIN_EMAIL,
            generate_password_hash(ADMIN_PASSWORD),
            "",
            "",
            ""
        ))

    # Remove admin role from any other account
    db.execute("""
        UPDATE users
        SET role='donor'
        WHERE email != ? AND role='admin'
    """, (ADMIN_EMAIL,))

    db.commit()


with app.app_context():
    init_db()


# ============================================================
# HELPERS
# ============================================================

def login_required():
    return "user_id" in session


def admin_required():
    return session.get("role") == "admin"


# ============================================================
# HOME
# ============================================================

@app.route("/")
def index():
    return render_template("index.html")


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        phone = request.form.get("phone", "").strip()
        blood_group = request.form.get("blood_group", "").strip()
        location = request.form.get("location", "").strip()
        role = request.form.get("role", "donor").strip().lower()

        # Never allow public registration as admin
        if role not in ["donor", "requester", "volunteer"]:
            role = "donor"

        if not name or not email or not password:
            flash("Please fill all required fields.", "danger")
            return redirect(url_for("register"))

        if email == ADMIN_EMAIL:
            flash("This email is reserved for the administrator.", "danger")
            return redirect(url_for("register"))

        db = get_db()

        existing = db.execute(
            "SELECT id FROM users WHERE email=?",
            (email,)
        ).fetchone()

        if existing:
            flash("An account with this email already exists.", "danger")
            return redirect(url_for("register"))

        db.execute("""
            INSERT INTO users
            (name, email, password, phone, blood_group, location, role, available)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            name,
            email,
            generate_password_hash(password),
            phone,
            blood_group,
            location,
            role
        ))

        db.commit()

        flash("Registration successful. Please login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


# ============================================================
# USER LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = get_db().execute(
            "SELECT * FROM users WHERE email=?",
            (email,)
        ).fetchone()

        if user and check_password_hash(user["password"], password):

            session.clear()

            session["user_id"] = user["id"]
            session["role"] = user["role"]
            session["name"] = user["name"]

            flash("Login successful.", "success")

            if user["role"] == "admin":
                return redirect(url_for("admin"))

            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


# ============================================================
# SEPARATE ADMIN LOGIN
# ============================================================

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if email != ADMIN_EMAIL:
            flash(
                "Only the system administrator can use this login.",
                "danger"
            )
            return redirect(url_for("admin_login"))

        user = get_db().execute("""
            SELECT * FROM users
            WHERE email=? AND role='admin'
        """, (email,)).fetchone()

        if user and check_password_hash(user["password"], password):

            session.clear()

            session["user_id"] = user["id"]
            session["role"] = "admin"
            session["name"] = user["name"]

            flash("Admin login successful.", "success")

            return redirect(url_for("admin"))

        flash("Invalid admin email or password.", "danger")

    # This page is built here so you do NOT need another HTML file.
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Admin Login - LifeLink</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <link
        href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
        rel="stylesheet"
    >
</head>

<body class="bg-light">

<div class="container mt-5">

    <div class="row justify-content-center">

        <div class="col-md-6">

            <div class="card shadow">

                <div class="card-body p-4">

                    <h2 class="text-center mb-4">
                        🔐 LifeLink Admin Login
                    </h2>

                    <p class="text-muted text-center">
                        Administrator access only
                    </p>

                    {% with messages = get_flashed
