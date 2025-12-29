from flask import Flask, render_template, request, redirect, session, jsonify
import sqlite3
from datetime import datetime, timedelta

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

    # USERS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        device_id TEXT,
        security_answer TEXT,
        reports INTEGER DEFAULT 0,
        muted_until TEXT
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

    # REPORT LOGS (one report per user per message)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS report_logs (
        message_id INTEGER,
        reporter TEXT,
        PRIMARY KEY (message_id, reporter)
    )
    """)

    # POLL
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
        u = request.form["username"]
        p = request.form["password"]
        d = request.form["device_id"]
        s = request.form["security_answer"]

        if p != LOGIN_PASSWORD:
            return render_template("login.html", error="Wrong password")

        con = db()
        cur = con.cursor()

        row = cur.execute(
            "SELECT device_id, security_answer FROM users WHERE username=?",
            (u,)
        ).fetchone()

        if row:
            if row[0] != d and row[1] != s:
                con.close()
                return render_template("login.html", error="Username locked")
            cur.execute(
                "UPDATE users SET device_id=? WHERE username=?",
                (d, u)
            )
        else:
            cur.execute(
                "INSERT INTO users(username,device_id,security_answer) VALUES(?,?,?)",
                (u, d, s)
            )

        con.commit()
        con.close()

        session["user"] = u
        if request.form.get("admin_password") == ADMIN_PASSWORD:
            session["admin"] = True
        else:
            session.pop("admin", None)

        return redirect("/chat")

    return render_template("login.html")

# ---------------- CHAT ----------------
@app.route("/chat")
def chat():
    if "user" not in session:
        return redirect("/")

    con = db()
    cur = con.cursor()

    mute = cur.execute(
        "SELECT muted_until FROM users WHERE username=?",
        (session["user"],)
    ).fetchone()

    muted = False
    if mute and mute[0]:
        if datetime.fromisoformat(mute[0]) > datetime.now():
            muted = True

    con.close()

    return render_template(
        "chat.html",
        user=session["user"],
        admin=session.get("admin"),
        muted=muted
    )

# ---------------- SEND MESSAGE (AJAX SAFE) ----------------
@app.route("/send", methods=["POST"])
def send():
    if "user" not in session:
        return "Unauthorized"

    con = db()
    cur = con.cursor()

    mute = cur.execute(
        "SELECT muted_until FROM users WHERE username=?",
        (session["user"],)
    ).fetchone()

    if mute and mute[0] and datetime.fromisoformat(mute[0]) > datetime.now():
        con.close()
        return "Muted"

    msg = request.form.get("msg", "").strip()
    if not msg:
        con.close()
        return "Empty"

    msg_type = "announcement" if session.get("admin") and request.form.get("announcement") else "normal"

    cur.execute(
        "INSERT INTO chat(user,message,msg_type,time) VALUES(?,?,?,?)",
        (session["user"], msg, msg_type, datetime.now().strftime("%H:%M"))
    )
    con.commit()
    con.close()

    return "OK"

# ---------------- AUTO REFRESH ----------------
@app.route("/messages")
def messages():
    con = db()
    data = con.execute(
        "SELECT id,user,message,msg_type,time FROM chat ORDER BY id ASC"
    ).fetchall()
    con.close()
    return jsonify(data)

# ---------------- REPORT (ONCE PER USER PER MESSAGE) ----------------
@app.route("/report/<int:mid>")
def report(mid):
    if "user" not in session:
        return redirect("/chat")

    con = db()
    cur = con.cursor()

    already = cur.execute(
        "SELECT 1 FROM report_logs WHERE message_id=? AND reporter=?",
        (mid, session["user"])
    ).fetchone()

    if already:
        con.close()
        return redirect("/chat")

    cur.execute(
        "INSERT INTO report_logs(message_id,reporter) VALUES(?,?)",
        (mid, session["user"])
    )

    owner = cur.execute(
        "SELECT user FROM chat WHERE id=?",
        (mid,)
    ).fetchone()

    if owner:
        cur.execute(
            "UPDATE users SET reports=reports+1 WHERE username=?",
            (owner[0],)
        )

    con.commit()
    con.close()
    return redirect("/chat")

# ---------------- ADMIN DELETE MESSAGE ----------------
@app.route("/delete_msg/<int:mid>")
def delete_msg(mid):
    if not session.get("admin"):
        return redirect("/chat")

    con = db()
    con.execute("DELETE FROM chat WHERE id=?", (mid,))
    con.commit()
    con.close()
    return redirect("/chat")

# ---------------- ADMIN MUTE USER ----------------
@app.route("/mute/<username>")
def mute(username):
    if not session.get("admin"):
        return redirect("/chat")

    until = datetime.now() + timedelta(minutes=30)

    con = db()
    con.execute(
        "UPDATE users SET muted_until=? WHERE username=?",
        (until.isoformat(), username)
    )
    con.commit()
    con.close()
    return redirect("/chat")

# ---------------- ADMIN PANEL ----------------
@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect("/chat")

    con = db()
    users = con.execute(
        "SELECT username,reports,muted_until FROM users"
    ).fetchall()
    con.close()

    return render_template("admin.html", users=users)

# ---------------- POLL ----------------
@app.route("/poll", methods=["GET", "POST"])
def poll():
    if "user" not in session:
        return redirect("/")

    con = db()
    cur = con.cursor()

    if request.method == "POST" and session.get("admin"):
        q  = request.form.get("question")
        o1 = request.form.get("o1")
        o2 = request.form.get("o2")
        o3 = request.form.get("o3")
        o4 = request.form.get("o4")

        # Create poll ONLY if all fields exist
        if q and o1 and o2 and o3 and o4:
            # Clear old poll safely
            cur.execute("DELETE FROM poll")
            cur.execute("DELETE FROM poll_votes")

            # ✅ 9 columns → 9 values (FIXED)
            cur.execute("""
                INSERT INTO poll
                (question, opt1, opt2, opt3, opt4, v1, v2, v3, v4)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (q, o1, o2, o3, o4, 0, 0, 0, 0))

            con.commit()

    poll = cur.execute("SELECT * FROM poll").fetchone()
    con.close()

    return render_template("poll.html", poll=poll, admin=session.get("admin"))


# ---------------- VOTE ----------------
@app.route("/vote/<int:n>")
def vote(n):
    if "user" not in session:
        return redirect("/")

    if n not in [1, 2, 3, 4]:
        return redirect("/poll")

    con = db()
    cur = con.cursor()

    already = cur.execute(
        "SELECT username FROM poll_votes WHERE username=?",
        (session["user"],)
    ).fetchone()

    if not already:
        cur.execute(f"UPDATE poll SET v{n} = v{n} + 1")
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
