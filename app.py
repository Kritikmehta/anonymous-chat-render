from flask import Flask, render_template, request, redirect, session
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "change_this_secret_key"

# 🔐 PASSWORDS
LOGIN_PASSWORD = "college123"
ADMIN_PASSWORD = "admin123"

# 📦 DATABASE CONNECTION (FIXED)
def db():
    con = sqlite3.connect(
        "database.db",
        timeout=10,
        check_same_thread=False
    )
    con.execute("PRAGMA journal_mode=WAL;")
    return con

# 🗄️ AUTO CREATE DATABASE TABLES
def init_db():
    con = db()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        username TEXT PRIMARY KEY,
        reports INTEGER DEFAULT 0,
        banned_until TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS chat(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT,
        message TEXT,
        time TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS poll(
        question TEXT,
        yes INTEGER,
        no INTEGER
    )
    """)

    con.commit()
    con.close()

init_db()

# ---------------- LOGIN ----------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form["password"] == LOGIN_PASSWORD:
            username = request.form["username"]

            con = db()
            con.execute(
                "INSERT OR IGNORE INTO users(username) VALUES(?)",
                (username,)
            )
            con.commit()
            con.close()

            session["user"] = username
            return redirect("/chat")

    return render_template("login.html")

# ---------------- CHAT ----------------
@app.route("/chat")
def chat():
    if "user" not in session:
        return redirect("/")

    con = db()
    cur = con.cursor()

    ban = cur.execute(
        "SELECT banned_until FROM users WHERE username=?",
        (session["user"],)
    ).fetchone()

    if ban and ban[0]:
        until = datetime.fromisoformat(ban[0])
        if until > datetime.now():
            con.close()
            return f"You are banned till {until}"

    messages = cur.execute(
        "SELECT user,message,time FROM chat ORDER BY id DESC LIMIT 50"
    ).fetchall()

    con.close()

    return render_template(
        "chat.html",
        messages=messages[::-1],
        user=session["user"]
    )

@app.route("/send", methods=["POST"])
def send():
    if "user" not in session:
        return redirect("/")

    msg = request.form["msg"]

    con = db()
    con.execute(
        "INSERT INTO chat(user,message,time) VALUES(?,?,?)",
        (session["user"], msg, datetime.now().strftime("%H:%M"))
    )
    con.commit()
    con.close()

    return redirect("/chat")

# ---------------- REPORT ----------------
@app.route("/report/<username>")
def report(username):
    con = db()
    cur = con.cursor()

    cur.execute(
        "UPDATE users SET reports = reports + 1 WHERE username=?",
        (username,)
    )

    reports = cur.execute(
        "SELECT reports FROM users WHERE username=?",
        (username,)
    ).fetchone()[0]

    if reports >= 5:
        ban_until = datetime.now() + timedelta(hours=2)
        cur.execute(
            "UPDATE users SET banned_until=? WHERE username=?",
            (ban_until.isoformat(), username)
        )

    con.commit()
    con.close()

    return redirect("/chat")

# ---------------- ADMIN ----------------
@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        if request.form["password"] == ADMIN_PASSWORD:
            session["admin"] = True

    if not session.get("admin"):
        return render_template("admin.html", login=True)

    con = db()
    users = con.execute(
        "SELECT username,reports,banned_until FROM users"
    ).fetchall()
    con.close()

    return render_template("admin.html", users=users)

@app.route("/delete/<username>")
def delete_user(username):
    if not session.get("admin"):
        return redirect("/")

    con = db()
    con.execute("DELETE FROM users WHERE username=?", (username,))
    con.commit()
    con.close()

    return redirect("/admin")

# ---------------- POLL ----------------
@app.route("/poll", methods=["GET", "POST"])
def poll():
    con = db()
    cur = con.cursor()

    if request.method == "POST" and session.get("admin"):
        cur.execute("DELETE FROM poll")
        cur.execute(
            "INSERT INTO poll(question,yes,no) VALUES(?,?,?)",
            (request.form["question"], 0, 0)
        )
        con.commit()

    poll_data = cur.execute("SELECT * FROM poll").fetchone()
    con.close()

    return render_template(
        "poll.html",
        poll=poll_data,
        admin=session.get("admin")
    )

@app.route("/vote/<opt>")
def vote(opt):
    con = db()
    con.execute(f"UPDATE poll SET {opt}={opt}+1")
    con.commit()
    con.close()

    return redirect("/poll")

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run()
