
import os, sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "lifelink.db")

app = Flask(__name__)
app.secret_key = os.environ.get("LIFELINK_SECRET_KEY", "change-this-secret-key")

BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
ROLES = ["donor", "requester", "volunteer"]

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
        FOREIGN KEY (requester_id) REFERENCES users(id) ON DELETE CASCADE
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
        FOREIGN KEY (requester_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS responses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER NOT NULL,
        donor_id INTEGER NOT NULL,
        response TEXT NOT NULL DEFAULT 'I Can Help',
        created_at TEXT NOT NULL,
        UNIQUE(request_id, donor_id),
        FOREIGN KEY (request_id) REFERENCES blood_requests(id) ON DELETE CASCADE,
        FOREIGN KEY (donor_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)
    # Demo admin account
    existing = db.execute("SELECT id FROM users WHERE email=?", ("admin@lifelink.local",)).fetchone()
    if not existing:
        db.execute(
            """INSERT INTO users
            (name,email,password,phone,role,blood_group,city,available,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            ("LifeLink Admin", "admin@lifelink.local",
             generate_password_hash("admin123"), "9999999999", "admin",
             None, "Bengaluru", 1, datetime.now().isoformat(timespec="seconds"))
        )
    db.commit()

@app.before_request
def before_request():
    init_db()

@app.context_processor
def inject_globals():
    return {"blood_groups": BLOOD_GROUPS}

@app.route("/")
def index():
    db = get_db()
    blood = db.execute("""SELECT br.*, u.name AS requester_name
                          FROM blood_requests br JOIN users u ON u.id=br.requester_id
                          WHERE br.status='Active' ORDER BY br.id DESC LIMIT 8""").fetchall()
    volunteers = db.execute("""SELECT vr.*, u.name AS requester_name
                               FROM volunteer_requests vr JOIN users u ON u.id=vr.requester_id
                               WHERE vr.status='Open' ORDER BY vr.id DESC LIMIT 8""").fetchall()
    return render_template("index.html", blood=blood, volunteers=volunteers)

@app.route("/register", methods=["GET","POST"])
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
        if role == "donor" and blood_group not in BLOOD_GROUPS:
            flash("Donors must select a valid blood group.", "danger")
            return redirect(url_for("register"))
        if len(password) < 6:
            flash("Password must contain at least 6 characters.", "danger")
            return redirect(url_for("register"))

        db = get_db()
        try:
            db.execute("""INSERT INTO users
                (name,email,password,phone,role,blood_group,city,available,created_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (name,email,generate_password_hash(password),phone,role,blood_group,city,1,
                 datetime.now().isoformat(timespec="seconds")))
            db.commit()
            flash("Registration successful. Please login.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("That email is already registered.", "danger")
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        user = get_db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            session["name"] = user["name"]
            flash("Welcome to LifeLink.", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))

def login_required():
    if "user_id" not in session:
        flash("Please login first.", "warning")
        return False
    return True

@app.route("/dashboard")
def dashboard():
    if not login_required():
        return redirect(url_for("login"))
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    requests = db.execute("""SELECT br.*, u.name AS requester_name
                             FROM blood_requests br JOIN users u ON u.id=br.requester_id
                             WHERE br.status='Active' ORDER BY br.id DESC""").fetchall()
    volunteers = db.execute("""SELECT vr.*, u.name AS requester_name
                               FROM volunteer_requests vr JOIN users u ON u.id=vr.requester_id
                               WHERE vr.status='Open' ORDER BY vr.id DESC""").fetchall()
    return render_template("dashboard.html", user=user, requests=requests, volunteers=volunteers)

@app.route("/blood-request", methods=["GET","POST"])
def blood_request():
    if not login_required():
        return redirect(url_for("login"))
    if request.method == "POST":
        db = get_db()
        db.execute("""INSERT INTO blood_requests
            (requester_id,blood_group,units,hospital,city,urgency,contact,notes,status,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (session["user_id"], request.form["blood_group"], int(request.form["units"]),
             request.form["hospital"].strip(), request.form["city"].strip(),
             request.form["urgency"], request.form["contact"].strip(),
             request.form.get("notes","").strip(), "Active",
             datetime.now().isoformat(timespec="seconds")))
        db.commit()
        flash("Blood request created.", "success")
        return redirect(url_for("dashboard"))
    return render_template("blood_request.html")

@app.route("/volunteer-request", methods=["GET","POST"])
def volunteer_request():
    if not login_required():
        return redirect(url_for("login"))
    if request.method == "POST":
        db = get_db()
        db.execute("""INSERT INTO volunteer_requests
            (requester_id,assistance,location,urgency,contact,notes,status,created_at)
            VALUES (?,?,?,?,?,?,?,?)""",
            (session["user_id"], request.form["assistance"].strip(),
             request.form["location"].strip(), request.form["urgency"],
             request.form["contact"].strip(), request.form.get("notes","").strip(),
             "Open", datetime.now().isoformat(timespec="seconds")))
        db.commit()
        flash("Volunteer request created.", "success")
        return redirect(url_for("dashboard"))
    return render_template("volunteer_request.html")

@app.route("/donors")
def donors():
    if not login_required():
        return redirect(url_for("login"))
    bg = request.args.get("blood_group","")
    city = request.args.get("city","").strip()
    sql = "SELECT * FROM users WHERE role='donor' AND available=1"
    params=[]
    if bg:
        sql += " AND blood_group=?"; params.append(bg)
    if city:
        sql += " AND city LIKE ?"; params.append(f"%{city}%")
    sql += " ORDER BY name"
    rows = get_db().execute(sql, params).fetchall()
    return render_template("donors.html", donors=rows, selected_bg=bg, selected_city=city)

@app.post("/respond/<int:request_id>")
def respond(request_id):
    if not login_required():
        return redirect(url_for("login"))
    if session.get("role") != "donor":
        flash("Only donor accounts can respond to blood requests.", "warning")
        return redirect(url_for("dashboard"))
    db=get_db()
    req=db.execute("SELECT * FROM blood_requests WHERE id=? AND status='Active'",(request_id,)).fetchone()
    if not req:
        flash("Request is not available.", "danger")
        return redirect(url_for("dashboard"))
    try:
        db.execute("INSERT INTO responses(request_id,donor_id,response,created_at) VALUES(?,?,?,?)",
                   (request_id,session["user_id"],"I Can Help",datetime.now().isoformat(timespec="seconds")))
        db.commit()
        flash("Your response has been recorded. Please contact the requester.", "success")
    except sqlite3.IntegrityError:
        flash("You have already responded to this request.", "info")
    return redirect(url_for("dashboard"))

@app.route("/admin")
def admin():
    if not login_required() or session.get("role") != "admin":
        flash("Admin access required.", "danger")
        return redirect(url_for("dashboard"))
    db=get_db()
    users=db.execute("SELECT id,name,email,phone,role,blood_group,city,available FROM users ORDER BY id DESC").fetchall()
    reqs=db.execute("""SELECT br.*,u.name requester_name FROM blood_requests br
                      JOIN users u ON u.id=br.requester_id ORDER BY br.id DESC""").fetchall()
    responses=db.execute("""SELECT r.*, u.name donor_name, br.blood_group, br.hospital
                            FROM responses r JOIN users u ON u.id=r.donor_id
                            JOIN blood_requests br ON br.id=r.request_id
                            ORDER BY r.id DESC""").fetchall()
    return render_template("admin.html", users=users, reqs=reqs, responses=responses)

@app.post("/admin/request/<int:request_id>/<status>")
def update_request(request_id,status):
    if not login_required() or session.get("role") != "admin":
        flash("Admin access required.", "danger")
        return redirect(url_for("dashboard"))
    if status not in ["Active","Fulfilled","Cancelled"]:
        flash("Invalid status.", "danger")
        return redirect(url_for("admin"))
    db=get_db()
    db.execute("UPDATE blood_requests SET status=? WHERE id=?",(status,request_id))
    db.commit()
    flash(f"Request marked {status}.", "success")
    return redirect(url_for("admin"))

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
