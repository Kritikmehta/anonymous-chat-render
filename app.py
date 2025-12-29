from flask import Flask, render_template, request, redirect, session, jsonify
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = "CHANGE_THIS_SECRET"

LOGIN_PASSWORD = "college123"
ADMIN_PASSWORD = "admin123"

# ---------------- DATABASE ----------------
def db():
    con = sqlite3.connect(
        "database.db",
        timeout=10,
        check_same_thread=False
    )
    con.execute("PRAGMA journal_mode=WAL;")
    return con

def init_db():
    con = db()
    cur = con.cursor()

    # USERS (username permanently reserved)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        device_id TEXT,
        security_answer TEXT,
        reports INTEGER DEFAULT 0,
        banned_until TEXT
    )
    """)

    # CHAT
    cur.execute("""
    CREATE TABLE IF NOT EXISTS chat (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT,
        message TEXT,
        msg_type TEXT,
        time TEXT
    )
    """)

    # POLL (4 options)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS poll (
        question TEXT,
        opt1 TEXT,
        opt2 TEXT,
        opt3 TEXT,
        opt4 TEXT,
        v1 INTEGER,
        v2 INTEGER,
        v3 INTEGER,
        v4 INTEGER
    )
    """)

    # POLL VOTES (one vote per username)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS poll_votes (
        username TEXT PRIMARY KEY
    )
    """)

    con.commit()
    con.close()

init_db()

# ---------------- LOGIN ----------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        device_id = request.form.get("device_id")
        sec_ans = request.form.get("security_answer")
        is_admin = request.form.get("is_admin")

        if password != LOGIN_PASSWORD:
            return render_template("login.html", error="Wrong password")

        con = db()
        cur = con.cursor()

        user = cur.execute(
            "SELECT device_id, security_answer FROM users WHERE username=?",
            (username,)
        ).fetchone()

        if user:
            # Username already exists (PERMANENTLY RESERVED)
            if user[0] == device_id:
                session["user"] = username
            elif sec_ans and sec_ans == user[1]:
                # Correct security answer → transfer ownership
                cur.execute(
                    "UPDATE users SET device_id=? WHERE username=?",
                    (device_id, username)
                )
                con.commit()
                session["user"] = username
            else:
                con.close()
                return render_template(
                    "login.html",
                    error="Username already taken or wrong security answer",
                    question="What name did you secretly use for someone you liked?"
                )
        else:
            # New username (PERMANENT)
            cur.execute(
                "INSERT INTO users(username, device_id, security_answer) VALUES(?,?,?)",
                (username, device_id, sec_ans)
            )
            con.commit()
            session["user"] = username

        # Admin flag (same user system)
        if is_admin and request.form.get("admin_password") == ADMIN_PASSWORD:
            session["admin"] = True
        else:
            session.pop("admin", None)

        con.close()
        return redirect("/chat")

    return render_template(
        "login.html",
        question="What name did you secretly use for someone you liked?"
    )

# ---------------- CHAT PAGE ----------------
@app.route("/chat")
def chat():
    if "user" not in session:
        return redirect("/")

    con = db()
    cur = con.cursor()

    # Get announcements first (pinned)
    announcements = cur.execute(
        "SELECT user,message,msg_type,time FROM chat WHERE msg_type='announcement' ORDER BY id DESC"
    ).fetchall()

    messages = cur.execute(
        "SELECT user,message,msg_type,time FROM chat WHERE msg_type='normal' ORDER BY id ASC"
    ).fetchall()

    con.close()

    return render_template(
        "chat.html",
        user=session["user"],
        admin=session.get("admin"),
        announcements=announcements,
        messages=messages
    )

# ---------------- SEND MESSAGE ----------------
@app.route("/send", methods=["POST"])
def send():
    if "user" not in session:
        return "Unauthorized"

    msg = request.form.get("msg")
    is_announcement = request.form.get("announcement") == "1"

    msg_type = "announcement" if session.get("admin") and is_announcement else "normal"

    con = db()
    con.execute(
        "INSERT INTO chat(user,message,msg_type,time) VALUES(?,?,?,?)",
        (session["user"], msg, msg_type, datetime.now().strftime("%H:%M"))
    )
    con.commit()
    con.close()

    return "OK"

# ---------------- AUTO REFRESH (JSON) ----------------
@app.route("/messages")
def messages():
    con = db()
    data = con.execute(
        "SELECT user,message,msg_type,time FROM chat ORDER BY id ASC"
    ).fetchall()
    con.close()
    return jsonify(data)

# ---------------- ADMIN PANEL ----------------
@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect("/chat")

    con = db()
    users = con.execute(
        "SELECT username,reports,banned_until FROM users"
    ).fetchall()
    con.close()

    return render_template("admin.html", users=users)

# ---------------- POLL ----------------
@app.route("/poll", methods=["GET", "POST"])
def poll():
    con = db()
    cur = con.cursor()

    if request.method == "POST" and session.get("admin"):
        cur.execute("DELETE FROM poll")
        cur.execute("DELETE FROM poll_votes")
        cur.execute("""
        INSERT INTO poll VALUES (?,?,?,?,?,?,?,?)
        """, (
            request.form["question"],
            request.form["o1"],
            request.form["o2"],
            request.form["o3"],
            request.form["o4"],
            0, 0, 0, 0
        ))
        con.commit()

    poll = cur.execute("SELECT * FROM poll").fetchone()
    con.close()

    return render_template("poll.html", poll=poll, admin=session.get("admin"))

# ---------------- VOTE ----------------
@app.route("/vote/<int:n>")
def vote(n):
    if "user" not in session:
        return redirect("/")

    con = db()
    cur = con.cursor()

    already = cur.execute(
        "SELECT username FROM poll_votes WHERE username=?",
        (session["user"],)
    ).fetchone()

    if not already:
        cur.execute(f"UPDATE poll SET v{n}=v{n}+1")
        cur.execute(
            "INSERT INTO poll_votes(username) VALUES(?)",
            (session["user"],)
        )
        con.commit()

    con.close()
    return redirect("/poll")

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run()
