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

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        device_id TEXT,
        security_answer TEXT,
        reports INTEGER DEFAULT 0,
        muted_until TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS chat (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT,
        message TEXT,
        msg_type TEXT,
        time TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS report_logs (
        message_id INTEGER,
        reporter TEXT,
        PRIMARY KEY (message_id, reporter)
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
            cur.execute("UPDATE users SET device_id=? WHERE username=?", (d, u))
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

    msgs = cur.execute(
        "SELECT id,user,message,msg_type,time FROM chat ORDER BY id ASC"
    ).fetchall()

    con.close()

    return render_template(
        "chat.html",
        messages=msgs,
        user=session["user"],
        admin=session.get("admin"),
        muted=muted
    )

# ---------------- SEND MESSAGE ----------------
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

    msg = request.form["msg"]
    mtype = "announcement" if session.get("admin") and request.form.get("announcement") else "normal"

    cur.execute(
        "INSERT INTO chat(user,message,msg_type,time) VALUES(?,?,?,?)",
        (session["user"], msg, mtype, datetime.now().strftime("%H:%M"))
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

# ---------------- REPORT (ONE TIME PER USER PER MESSAGE) ----------------
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

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run()
