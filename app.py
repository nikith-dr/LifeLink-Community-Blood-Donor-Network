import os
import sqlite3
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__)

app.secret_key = os.environ.get(
    "LIFELINK_SECRET_KEY",
    "lifelink-secret-key-2026"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "lifelink.db")

BLOOD_GROUPS = [
    "A+", "A-", "B+", "B-",
    "AB+", "AB-", "O+", "O-"
]

ROLES = [
    "donor",
    "requester",
    "volunteer"
]

ADMIN_EMAIL = "nikithdr@gmail.com"
ADMIN_PASSWORD = "niki@2007"
ADMIN_NAME = "Nikith D R"


# =========================================================
# DATABASE
# =========================================================

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

    # Remove admin role from everyone except the official admin
    db.execute("""
        UPDATE users
        SET role='volunteer'
        WHERE role='admin'
        AND email != ?
    """, (ADMIN_EMAIL,))

    # Create official admin if it doesn't exist
    admin = db.execute(
        "SELECT id FROM users WHERE email=?",
        (ADMIN_EMAIL,)
    ).fetchone()

    if admin is None:
        db.execute("""
            INSERT INTO users
            (
                name,
                email,
                password,
                phone,
                role,
                blood_group,
                city,
                available,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ADMIN_NAME,
            ADMIN_EMAIL,
            generate_password_hash(ADMIN_PASSWORD),
            "9999999999",
            "admin",
            None,
            "Bengaluru",
            1,
            datetime.now().isoformat(timespec="seconds")
        ))
    else:
        # Keep official admin credentials correct
        db.execute("""
            UPDATE users
            SET name=?,
                password=?,
                role='admin'
            WHERE email=?
        """, (
            ADMIN_NAME,
            generate_password_hash(ADMIN_PASSWORD),
            ADMIN_EMAIL
        ))

    db.commit()


@app.before_request
def before_request():
    init_db()


@app.context_processor
def inject_globals():
    return {
        "blood_groups": BLOOD_GROUPS
    }


# =========================================================
# HOME
# =========================================================

@app.route("/")
def index():
    return render_template("index.html")


# =========================================================
# REGISTER
# =========================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        phone = request.form["phone"].strip()
        role = request.form["role"].strip()
        blood_group = request.form.get("blood_group") or None
        city = request.form["city"].strip()

        if email == ADMIN_EMAIL:
            flash(
                "This email is reserved for the administrator.",
                "danger"
            )
            return redirect(url_for("register"))

        if role not in ROLES:
            flash("Invalid role.", "danger")
            return redirect(url_for("register"))

        if role == "donor" and blood_group not in BLOOD_GROUPS:
            flash(
                "Please select a valid blood group.",
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
            db.execute("""
                INSERT INTO users
                (
                    name,
                    email,
                    password,
                    phone,
                    role,
                    blood_group,
                    city,
                    available,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name,
                email,
                generate_password_hash(password),
                phone,
                role,
                blood_group,
                city,
                1,
                datetime.now().isoformat(timespec="seconds")
            ))

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


# =========================================================
# USER LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"].strip().lower()
        password = request.form["password"]

        # Admin must use separate login
        if email == ADMIN_EMAIL:
            flash(
                "Please use the separate Admin Login.",
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


# =========================================================
# SEPARATE ADMIN LOGIN
# =========================================================

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if email != ADMIN_EMAIL:
            flash(
                "Only the system administrator can use this login.",
                "danger"
            )
            return redirect(url_for("admin_login"))

        user = get_db().execute("""
            SELECT *
            FROM users
            WHERE email=?
            AND role='admin'
        """, (email,)).fetchone()

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


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    flash(
        "You have been logged out.",
        "info"
    )

    return redirect(url_for("index"))


# =========================================================
# USER DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    db = get_db()

    user = db.execute(
        "SELECT * FROM users WHERE id=?",
        (session["user_id"],)
    ).fetchone()

    requests_list = db.execute("""
        SELECT
            br.*,
            u.name AS requester_name
        FROM blood_requests br
        JOIN users u
        ON u.id = br.requester_id
        WHERE br.status='Active'
        ORDER BY br.id DESC
    """).fetchall()

    volunteers = db.execute("""
        SELECT
            vr.*,
            u.name AS requester_name
        FROM volunteer_requests vr
        JOIN users u
        ON u.id = vr.requester_id
        WHERE vr.status='Open'
        ORDER BY vr.id DESC
    """).fetchall()

    return render_template(
        "dashboard.html",
        user=user,
        requests=requests_list,
        volunteers=volunteers
    )


# =========================================================
# BLOOD REQUEST
# =========================================================

@app.route("/blood-request", methods=["GET", "POST"])
def blood_request():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        blood_group = request.form["blood_group"]
        units = int(request.form["units"])
        hospital = request.form["hospital"].strip()
        city = request.form["city"].strip()
        urgency = request.form["urgency"]
        contact = request.form["contact"].strip()
        notes = request.form.get("notes", "").strip()

        db = get_db()

        db.execute("""
            INSERT INTO blood_requests
            (
                requester_id,
                blood_group,
                units,
                hospital,
                city,
                urgency,
                contact,
                notes,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Active', ?)
        """, (
            session["user_id"],
            blood_group,
            units,
            hospital,
            city,
            urgency,
            contact,
            notes,
            datetime.now().isoformat(timespec="seconds")
        ))

        db.commit()

        flash(
            "Blood request published successfully.",
            "success"
        )

        return redirect(url_for("dashboard"))

    return render_template("blood_request.html")


# =========================================================
# VOLUNTEER REQUEST
# =========================================================

@app.route("/volunteer-request", methods=["GET", "POST"])
def volunteer_request():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        assistance = request.form["assistance"].strip()
        urgency = request.form["urgency"]
        location = request.form["location"].strip()
        contact = request.form["contact"].strip()
        notes = request.form.get("notes", "").strip()

        db = get_db()

        db.execute("""
            INSERT INTO volunteer_requests
            (
                requester_id,
                assistance,
                location,
                urgency,
                contact,
                notes,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'Open', ?)
        """, (
            session["user_id"],
            assistance,
            location,
            urgency,
            contact,
            notes,
            datetime.now().isoformat(timespec="seconds")
        ))

        db.commit()

        flash(
            "Volunteer request published successfully.",
            "success"
        )

        return redirect(url_for("dashboard"))

    return render_template("volunteer_request.html")


# =========================================================
# FIND DONORS
# =========================================================

@app.route("/donors")
def donors():

    if "user_id" not in session:
        return redirect(url_for("login"))

    selected_bg = request.args.get(
        "blood_group",
        ""
    ).strip()

    selected_city = request.args.get(
        "city",
        ""
    ).strip()

    query = """
        SELECT *
        FROM users
        WHERE role='donor'
        AND available=1
    """

    params = []

    if selected_bg:
        query += " AND blood_group=?"
        params.append(selected_bg)

    if selected_city:
        query += " AND city LIKE ?"
        params.append("%" + selected_city + "%")

    query += " ORDER BY name"

    donor_list = get_db().execute(
        query,
        params
    ).fetchall()

    return render_template(
        "donors.html",
        donors=donor_list,
        selected_bg=selected_bg,
        selected_city=selected_city
    )


# =========================================================
# DONOR RESPONSE
# =========================================================

@app.route(
    "/respond/<int:request_id>",
    methods=["POST"]
)
def respond(request_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "donor":
        flash(
            "Only donors can respond to blood requests.",
            "warning"
        )
        return redirect(url_for("dashboard"))

    db = get_db()

    existing = db.execute("""
        SELECT id
        FROM responses
        WHERE request_id=?
        AND donor_id=?
    """, (
        request_id,
        session["user_id"]
    )).fetchone()

    if existing:
        flash(
            "You already responded to this request.",
            "warning"
        )
        return redirect(url_for("dashboard"))

    db.execute("""
        INSERT INTO responses
        (
            request_id,
            donor_id,
            response,
            created_at
        )
        VALUES (?, ?, 'I Can Help', ?)
    """, (
        request_id,
        session["user_id"],
        datetime.now().isoformat(timespec="seconds")
    ))

    db.commit()

    flash(
        "Thank you! Your response was sent.",
        "success"
    )

    return redirect(url_for("dashboard"))


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin")
def admin():

    if session.get("role") != "admin":
        return redirect(url_for("admin_login"))

    db = get_db()

    users = db.execute("""
        SELECT *
        FROM users
        ORDER BY id DESC
    """).fetchall()

    reqs = db.execute("""
        SELECT
            br.*,
            u.name AS requester_name
        FROM blood_requests br
        JOIN users u
        ON u.id = br.requester_id
        ORDER BY br.id DESC
    """).fetchall()

    responses = db.execute("""
        SELECT
            r.*,
            u.name AS donor_name,
            br.blood_group,
            br.hospital
        FROM responses r
        JOIN users u
        ON u.id = r.donor_id
        JOIN blood_requests br
        ON br.id = r.request_id
        ORDER BY r.id DESC
    """).fetchall()

    return render_template(
        "admin.html",
        users=users,
        reqs=reqs,
        responses=responses
    )


# =========================================================
# ADMIN - UPDATE REQUEST
# =========================================================

@app.route(
    "/admin/request/<int:request_id>/<status>",
    methods=["POST"]
)
def update_request(request_id, status):

    if session.get("role") != "admin":
        return redirect(url_for("admin_login"))

    allowed = [
        "Active",
        "Fulfilled",
        "Cancelled"
    ]

    if status not in allowed:
        flash(
            "Invalid request status.",
            "danger"
        )
        return redirect(url_for("admin"))

    db = get_db()

    db.execute("""
        UPDATE blood_requests
        SET status=?
        WHERE id=?
    """, (
        status,
        request_id
    ))

    db.commit()

    flash(
        "Blood request status updated.",
        "success"
    )

    return redirect(url_for("admin"))


# =========================================================
# ADMIN - CHANGE USER ROLE
# =========================================================

@app.route(
    "/admin/user/<int:user_id>/role",
    methods=["POST"]
)
def admin_user_role(user_id):

    if session.get("role") != "admin":
        return redirect(url_for("admin_login"))

    role = request.form.get("role")

    if role not in ROLES:
        flash(
            "Invalid role.",
            "danger"
        )
        return redirect(url_for("admin"))

    db = get_db()

    user = db.execute(
        "SELECT * FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    if user is None:
        flash(
            "User not found.",
            "danger"
        )
        return redirect(url_for("admin"))

    if user["email"] == ADMIN_EMAIL:
        flash(
            "The main administrator cannot be changed.",
            "danger"
        )
        return redirect(url_for("admin"))

    db.execute("""
        UPDATE users
        SET role=?
        WHERE id=?
    """, (
        role,
        user_id
    ))

    db.commit()

    flash(
        "User role updated.",
        "success"
    )

    return redirect(url_for("admin"))


# =========================================================
# ADMIN - AVAILABILITY
# =================================
