import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, render_template_string, request
from flask import redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "lifelink-secret-key-2026"
)

DB = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "lifelink.db"
)

BLOOD_GROUPS = [
    "A+", "A-", "B+", "B-",
    "AB+", "AB-", "O+", "O-"
]

ADMIN_EMAIL = "nikithdr@gmail.com"
ADMIN_PASSWORD = "niki@2007"
ADMIN_NAME = "Nikith D R"


# =========================================================
# DATABASE
# =========================================================

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)

    if db:
        db.close()


def now():
    return datetime.now().isoformat(timespec="seconds")


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
            FOREIGN KEY(requester_id)
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
            FOREIGN KEY(requester_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL,
            donor_id INTEGER NOT NULL,
            response TEXT DEFAULT 'I Can Help',
            created_at TEXT NOT NULL,
            UNIQUE(request_id, donor_id),
            FOREIGN KEY(request_id)
                REFERENCES blood_requests(id)
                ON DELETE CASCADE,
            FOREIGN KEY(donor_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        );
    """)

    admin = db.execute(
        "SELECT id FROM users WHERE email=?",
        (ADMIN_EMAIL,)
    ).fetchone()

    if admin:
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
    else:
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
            VALUES (?, ?, ?, ?, 'admin', NULL, ?, 1, ?)
        """, (
            ADMIN_NAME,
            ADMIN_EMAIL,
            generate_password_hash(ADMIN_PASSWORD),
            "",
            "Bengaluru",
            now()
        ))

    db.execute("""
        UPDATE users
        SET role='donor'
        WHERE role='admin'
        AND email != ?
    """, (ADMIN_EMAIL,))

    db.commit()


@app.before_request
def start_app():
    init_db()


@app.context_processor
def globals_for_templates():
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
        role = request.form.get("role", "donor")
        blood_group = request.form.get("blood_group") or None
        city = request.form["city"].strip()

        if email == ADMIN_EMAIL:
            flash(
                "This email is reserved for the administrator.",
                "danger"
            )
            return redirect(url_for("register"))

        if role not in ["donor", "requester", "volunteer"]:
            role = "donor"

        if role == "donor":
            if blood_group not in BLOOD_GROUPS:
                flash(
                    "Please select a valid blood group.",
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
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            """, (
                name,
                email,
                generate_password_hash(password),
                phone,
                role,
                blood_group,
                city,
                now()
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

        user = get_db().execute("""
            SELECT *
            FROM users
            WHERE email=?
            AND role='admin'
        """, (email,)).fetchone()

        if (
            email == ADMIN_EMAIL
            and user
            and check_password_hash(
                user["password"],
                password
            )
        ):

            session.clear()

            session["user_id"] = user["id"]
            session["role"] = "admin"
            session["name"] = user["name"]

            return redirect(url_for("admin"))

        flash(
            "Invalid admin email or password.",
            "danger"
        )

    return render_template_string("""
<!doctype html>
<html>
<head>
    <title>LifeLink Admin Login</title>
    <meta name="viewport"
          content="width=device-width, initial-scale=1">

    <link
      href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
      rel="stylesheet">
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

{% with messages =
    get_flashed_messages(with_categories=true) %}

{% for category, message in messages %}

<div class="alert alert-{{ category }}">
    {{ message }}
</div>

{% endfor %}

{% endwith %}

<form method="post">

<label class="form-label">
    Admin Email
</label>

<input
    type="email"
    name="email"
    class="form-control mb-3"
    required
>

<label class="form-label">
    Admin Password
</label>

<input
    type="password"
    name="password"
    class="form-control mb-3"
    required
>

<button
    class="btn btn-danger w-100"
    type="submit">

    🔐 Login as Admin

</button>

</form>

<div class="text-center mt-3">

<a href="{{ url_for('login') }}">
    Back to User Login
</a>

</div>

<div class="text-center mt-2">

<a href="{{ url_for('index') }}">
    Back to Home
</a>

</div>

</div>
</div>

</div>
</div>

</div>

</body>
</html>
""")


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("index"))


# =========================================================
# DASHBOARD
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

    requests = db.execute("""
        SELECT *
        FROM blood_requests
        WHERE status='Active'
        ORDER BY id DESC
    """).fetchall()

    volunteers = db.execute("""
        SELECT *
        FROM volunteer_requests
        WHERE status='Open'
        ORDER BY id DESC
    """).fetchall()

    return render_template(
        "dashboard.html",
        user=user,
        requests=requests,
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
            request.form["blood_group"],
            int(request.form["units"]),
            request.form["hospital"].strip(),
            request.form["city"].strip(),
            request.form["urgency"],
            request.form["contact"].strip(),
            request.form.get("notes", "").strip(),
            now()
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
            request.form["assistance"].strip(),
            request.form["location"].strip(),
            request.form["urgency"],
            request.form["contact"].strip(),
            request.form.get("notes", "").strip(),
            now()
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

    blood_group = request.args.get(
        "blood_group",
        ""
    ).strip()

    city = request.args.get(
        "city",
        ""
    ).strip()

    query = """
        SELECT *
        FROM users
        WHERE role='donor'
        AND available=1
    """

    values = []

    if blood_group:
        query += " AND blood_group=?"
        values.append(blood_group)

    if city:
        query += " AND city LIKE ?"
        values.append("%" + city + "%")

    query += " ORDER BY name"

    donor_list = get_db().execute(
        query,
        values
    ).fetchall()

    return render_template(
        "donors.html",
        donors=donor_list,
        selected_bg=blood_group,
        selected_city=city
    )


# =========================================================
# DONOR RESPONSE
# =========================================================

@app.route("/respond/<int:request_id>", methods=["POST"])
def respond(request_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "donor":

        flash(
            "Only donors can respond.",
            "warning"
        )

        return redirect(url_for("dashboard"))

    db = get_db()

    try:

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
            now()
        ))

        db.commit()

        flash(
            "Your response was sent.",
            "success"
        )

    except sqlite3.IntegrityError:

        flash(
            "You already responded to this request.",
            "warning"
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

    users = db.execute(
        "SELECT * FROM users ORDER BY id DESC"
    ).fetchall()

    requests = db.execute(
        "SELECT * FROM blood_requests ORDER BY id DESC"
    ).fetchall()

    responses = db.execute("""
        SELECT
            responses.*,
            users.name AS donor_name,
            blood_requests.blood_group,
            blood_requests.hospital
        FROM responses
        JOIN users
        ON users.id = responses.donor_id
        JOIN blood_requests
        ON blood_requests.id = responses.request_id
        ORDER BY responses.id DESC
    """).fetchall()

    return render_template_string("""
<!doctype html>
<html>
<head>

<title>LifeLink Admin</title>

<meta name="viewport"
      content="width=device-width, initial-scale=1">

<link
href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
rel="stylesheet">

</head>

<body>

<div class="container py-4">

<div class="d-flex justify-content-between">

<h2>🔐 LifeLink Admin Dashboard</h2>

<a
class="btn btn-outline-danger"
href="{{ url_for('logout') }}">

Logout

</a>

</div>

<hr>

<h4>Registered Users</h4>

<div class="table-responsive">

<table class="table table-bordered">

<tr>
<th>Name</th>
<th>Email</th>
<th>Role</th>
<th>Blood</th>
<th>City</th>
<th>Action</th>
</tr>

{% for u in users %}

<tr>

<td>{{ u.name }}</td>
<td>{{ u.email }}</td>
<td>{{ u.role }}</td>
<td>{{ u.blood_group or '-' }}</td>
<td>{{ u.city }}</td>

<td>

{% if u.email != admin_email %}

<form
method="post"
action="{{ url_for('admin_delete_user', user_id=u.id) }}">

<button class="btn btn-sm btn-danger">
Delete
</button>

</form>

{% else %}

<b>Main Admin</b>

{% endif %}

</td>

</tr>

{% endfor %}

</table>

</div>

<h4 class="mt-4">Blood Requests</h4>

{% for r in requests %}

<div class="card mb-2">

<div class="card-body">

<b>
{{ r.blood_group }}
-
{{ r.units }} unit(s)
</b>

<br>

{{ r.hospital }},
{{ r.city }}

<br>

Urgency:
{{ r.urgency }}

<br>

Status:
<b>{{ r.status }}</b>

<br><br>

<form
method="post"
action="{{ url_for(
'admin_status',
request_id=r.id,
status='Fulfilled'
) }}"
style="display:inline">

<button class="btn btn-sm btn-success">
Mark Fulfilled
</button>

</form>

<form
method="post"
action="{{ url_for(
'admin_delete_request',
request_id=r.id
) }}"
style="display:inline">

<button class="btn btn-sm btn-danger">
Delete
</button>

</form>

</div>
</div>

{% else %}

<p>No blood requests.</p>

{% endfor %}


<h4 class="mt-4">
Donor Responses
</h4>

{% for r in responses %}

<div class="border rounded p-3 mb-2">

<b>{{ r.donor_name }}</b>

responded for

<b>{{ r.blood_group }}</b>

at {{ r.hospital }}

<br>

<form
method="post"
action="{{ url_for(
'admin_delete_response',
response_id=r.id
) }}">

<button class="btn btn-sm btn-danger mt-2">
Delete
</button>

</form>

</div>

{% else %}

<p>No responses.</p>

{% endfor %}

</div>

</body>
</html>
""",
        users=users,
        requests=requests,
        responses=responses,
        admin_email=ADMIN_EMAIL
    )


# =========================================================
# ADMIN ACTIONS
# =========================================================

@app.route(
    "/admin/request/<int:request_id>/<status>",
    methods=["POST"]
)
def admin_status(request_id, status):

    if session.get("role") != "admin":
        return redirect(url_for("admin_login"))

    if status not in [
        "Active",
        "Fulfilled",
        "Cancelled"
    ]:
                return redirect(url_for("admin"))

    db = get_db()

    db.execute(
        "UPDATE blood_requests SET status=? WHERE id=?",
        (status, request_id)
    )

    db.commit()

    flash("Blood request status updated.", "success")
    return redirect(url_for("admin"))


# ============================================================
# ADMIN - USER ROLE
# ============================================================

@app.route("/admin/user/<int:user_id>/role", methods=["POST"])
def admin_user_role(user_id):
    if session.get("role") != "admin":
        return redirect(url_for("admin_login"))

    role = request.form.get("role", "").strip()

    if role not in ["donor", "requester", "volunteer", "admin"]:
        flash("Invalid role.", "danger")
        return redirect(url_for("admin"))

    db = get_db()

    # Keep only the main administrator as admin
    if role == "admin":
        flash("The main administrator cannot be changed here.", "warning")
        return redirect(url_for("admin"))

    db.execute(
        "UPDATE users SET role=? WHERE id=?",
        (role, user_id)
    )
    db.commit()

    flash("User role updated.", "success")
    return redirect(url_for("admin"))


# ============================================================
# ADMIN - AVAILABILITY
# ============================================================

@app.route("/admin/user/<int:user_id>/availability", methods=["POST"])
def admin_availability(user_id):
    if session.get("role") != "admin":
        return redirect(url_for("admin_login"))

    available = request.form.get("available", "0")

    db = get_db()

    db.execute(
        "UPDATE users SET available=? WHERE id=?",
        (1 if available == "1" else 0, user_id)
    )

    db.commit()

    flash("Availability updated.", "success")
    return redirect(url_for("admin"))


# ============================================================
# ADMIN - DELETE USER
# ============================================================

@app.route("/admin/user/<int:user_id>/delete", methods=["POST"])
def admin_delete_user(user_id):
    if session.get("role") != "admin":
        return redirect(url_for("admin_login"))

    db = get_db()

    user = db.execute(
        "SELECT * FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("admin"))

    if user["email"] == ADMIN_EMAIL:
        flash("The main administrator cannot be deleted.", "danger")
        return redirect(url_for("admin"))

    db.execute(
        "DELETE FROM responses WHERE donor_id=?",
        (user_id,)
    )

    db.execute(
        "DELETE FROM users WHERE id=?",
        (user_id,)
    )

    db.commit()

    flash("User deleted successfully.", "success")
    return redirect(url_for("admin"))


# ============================================================
# ADMIN - DELETE BLOOD REQUEST
# ============================================================

@app.route("/admin/blood-request/<int:request_id>/delete", methods=["POST"])
def admin_delete_request(request_id):
    if session.get("role") != "admin":
        return redirect(url_for("admin_login"))

    db = get_db()

    db.execute(
        "DELETE FROM responses WHERE request_id=?",
        (request_id,)
    )

    db.execute(
        "DELETE FROM blood_requests WHERE id=?",
        (request_id,)
    )

    db.commit()

    flash("Blood request deleted.", "success")
    return redirect(url_for("admin"))


# ============================================================
# ADMIN - DELETE VOLUNTEER REQUEST
# ============================================================

@app.route("/admin/volunteer-request/<int:request_id>/delete", methods=["POST"])
def admin_delete_volunteer_request(request_id):
    if session.get("role") != "admin":
        return redirect(url_for("admin_login"))

    db = get_db()

    db.execute(
        "DELETE FROM volunteer_requests WHERE id=?",
        (request_id,)
    )

    db.commit()

    flash("Volunteer request deleted.", "success")
    return redirect(url_for("admin"))


# ============================================================
# ADMIN - DELETE RESPONSE
# ============================================================

@app.route("/admin/response/<int:response_id>/delete", methods=["POST"])
def admin_delete_response(response_id):
    if session.get("role") != "admin":
        return redirect(url_for("admin_login"))

    db = get_db()

    db.execute(
        "DELETE FROM responses WHERE id=?",
        (response_id,)
    )

    db.commit()

    flash("Donor response deleted.", "success")
    return redirect(url_for("admin"))


# ============================================================
# RUN APPLICATION
# ============================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
