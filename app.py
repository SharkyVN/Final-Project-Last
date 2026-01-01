from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import json
from datetime import datetime
from pathlib import Path 
from markupsafe import Markup

app = Flask(__name__)
app.secret_key = "dev-secret"

# --------- PATHS ---------- #
BASE = Path(".")
DATA = BASE / "data"
DATA.mkdir(exist_ok=True)

USERS_FILE = DATA / "users.json"
NOTES_FILE = DATA / "notes.json"
SCHEDULE_FILE = DATA / "schedule.json"
QUEST_POOL = [
    ("write_note", "Write a note"),
    ("add_event", "Add a schedule event"),
    ("check_notifications", "Check notifications"),
    ("use_darkmode", "Use dark mode"),
    ("edit_profile", "Update your profile"),
]

# --------- JSON HEPLERS ----------- #
def load_json(path, default=None):
    if not path.exists():
        return default if default is not None else []
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return default if default is not None else []
            return json.loads(content)
    except json.JSONDecodeError:
        return default if default is not None else []

def save_json(path, data):
    with open(path,"w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

for f in [USERS_FILE, NOTES_FILE, SCHEDULE_FILE]:
    if not f.exists():
        save_json(f, [])
# --------- USER HELPERS ------------ #
def load_users():
    return load_json(USERS_FILE)

def save_users(users):
    save_json(USERS_FILE, users)

# --------- BASIC HELPERS ------------#
def current_user():
    return session.get("username")

def parse_dt(value):
    try:
        return datetime.fromisoformat(value)
    except:
        return None

def today_str():
    return datetime.now().strftime("%Y-%m-%d")

def get_user_notes(username):
    return [n for n in load_json(NOTES_FILE) if n["owner"] == username]

def get_user_events(username):
    return [e for e in load_json(SCHEDULE_FILE) if e["owner"] == username]

def mark_quest_done(name):
    today = today_str()
    quests = session.get("quests_done", {})
    quests[f"{today}:{name}"] = True
    session["quests_done"] = quests

def quest_done(name):
    today = today_str()
    return session.get("quests_done", {}).get(f"{today}:{name}", False)

# ---------- NOTIFICATIONS ------------#
def compute_notifications(username):
    now = datetime.now()
    notifications = []

    # Events
    for event in load_json(SCHEDULE_FILE):
        if event.get("owner") != username:
            continue
        t = parse_dt(event.get("time"))
        if not t:
            continue
        seconds = int((t - now).total_seconds())
        notifications.append({
            "id": f"event-{event['id']}",
            "title": event.get("title"),
            "details": event.get("details",""),
            "time": t.strftime("%Y-%m-%d %H:%M"),
            "seconds_left":seconds,
            "soon": 0 < seconds <= 3600
    })

    # Notes with schedule
    for note in load_json(NOTES_FILE):
        if note.get("owner") != username or not note.get("schedule"):
            continue
        t = parse_dt(note["schedule"])
        if not t:
            continue
        seconds = int((t-now).total_seconds())
        notifications.append({
            "id": f"note-{note['id']}",
            "title": f"Note: {note.get('title')}",
            "details": note.get("category",""),
            "time": t.strftime("%Y-%m-%d %H:%M"),
            "seconds_left":seconds,
            "soon": 0 < seconds <= 3600
    })

    return notifications

def notification_count(username):
    return sum(1 for n in compute_notifications(username) if 0 < n["seconds_left"] <= 3600)

# ------------ MAKE FUNCTIONS AVAILABLE IN TEMPLATES ---------- #
app.jinja_env.globals.update(
    current_user=current_user,
    notification_count=notification_count
)

# ------------DAILY QUEST ---------- #
def compute_daily_quests(username):
    users = load_users()
    user = next((u for u in users if u["username"] == username), None)
    if not user:
        return{}

    today = today_str()

    if user.get("quest_date") != today:
        import random
        selected = random.sample(QUEST_POOL, 3)
        user["quests"] = {qid: False for qid, _ in selected}
        user["quest_labels"] = {qid: label for qid, label in selected}
        user["quest_date"] = today

    quests = user["quests"]

    # Write note
    if not quests.get("write_note"):
        note_today = [
            n for n in get_user_notes(username)
            if n.get("created") == today
        ]
        if note_today:
            quests["write_note"] = True

    # Add schedule
    if not quests.get("add_event"):
        events_today = [
            e for e in get_user_events(username)
            if parse_dt(e.get("time"))
            and parse_dt(e.get("time")).strftime("%Y-%m-%d") == today   
        ]   
        if events_today:
            quests["add_event"] = True

    # Check notifications
    if session.get("checked_notifications"):
        quests["check_notifications"] = True

    #Dark mode
    if session.get("darkmode"):
        quests["use_darkmode"] = True

    save_users(users)
    return quests

def ensure_daily_quests(user):
    today = today_str()
    if user.get("quest_date") != today:
        import random
        selected = random.sample(QUEST_POOL, 3)
        user["quests"] = {qid: False for qid, _ in selected}
        user["quest_labels"] = {qid: label for qid, label in selected}
        user["quest_date"] = today
# ------------ ROUTES ---------- #
@app.route("/")
def index():
    if not current_user():
        return redirect(url_for("login"))

    q = request.args.get("q","").lower()
    notes = get_user_notes(current_user())
    events = get_user_events(current_user())

    if q:
        notes = [n for n in notes if q in n["title"].lower() or q in n["content"].lower()]
        events = [e for e in events if q in e["title"].lower() or q in e.get("details","").lower()]

    quest = compute_daily_quests(current_user())

    return render_template("index.html", notes=notes, events=events, quests=quest)
# ------------ NOTES ------------ #
@app.route("/note/new", methods=["GET","POST"])
def new_note():
    if not current_user():
        return redirect(url_for("login"))

    if request.method == "POST":
        notes = load_json(NOTES_FILE)
        notes.append({
            "id": max([n["id"] for n in notes], default=0) + 1,
            "owner": current_user(),
            "title": request.form["title"],
            "category": request.form.get("category",""),
            "content": request.form["content"],
            "schedule": request.form.get("schedule",""),
            "created": today_str()
        })
        save_json(NOTES_FILE, notes)
        return redirect(url_for("index"))

    return render_template("new_note.html")

@app.route("/note/edit/<int:note_id>", methods=["GET","POST"])
def edit_note(note_id):
    if not current_user():
        return redirect(url_for("login"))

    notes = load_json(NOTES_FILE)
    note = next((n for n in notes if n["id"] == note_id and n ["owner"] == current_user()), None)
    if not note:
         return redirect(url_for("index"))

    if request.method == "POST":
        note["title"] = request.form["title"]
        note["category"] = request.form["category"]
        note["content"] = request.form["content"]
        note["schedule"] = request.form.get("schedule", "")
        save_json(NOTES_FILE, notes)
        return redirect(url_for("index"))
        
    return render_template("edit_note.html")

@app.route("/note/delete/<int:note_id>", methods=["POST"])
def delete_note(note_id):
    if not current_user():
        return redirect(url_for("login"))

    notes = [ n for n in load_json(NOTES_FILE)
            if not (n["id"] == note_id and n["owner"] == current_user())]
    save_json(NOTES_FILE, notes)
    flash("Note deleted")
    return redirect(url_for("index"))

# --------------- AUTHENTIC --------------- #
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form.get("email", "")
        avatar = request.form.get("avatar", "")

        users = load_users()
        user = next((u for u in users if u["username"]==username), None)

        if not user:
            users.append({
                "username":username,
                "email": email, 
                "avatar": avatar,
                "dark_mode": False,
                "quest": {},
                "quest_labels": {},
                "quest_date":""
            })
            save_users(users)
            flash(f"User {username} created and logged in", "success")
        else:
            if email:
                user["email"] = email
            if avatar:
                user["avatar"] = avatar
        save_users(users)
        flash(f"Logged in as {username}", "success")

        session["username"] = username
        return redirect(url_for("index"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return render_template("login.html")

# ------------ REGISTER -------- #
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form.get("email", "")
        avatar = request.form.get("avatar","")

        users = load_users()
        if any(u["username"] == username for u in users):
            flash("User already exists", "danger")
            return redirect(url_for("register"))

        users.append({
                "username":username,
                "email": email, 
                "avatar": avatar,
                "dark_mode": False,
                "quest": {},
                "quest_labels": {},
                "quest_date":""
            })
        save_users(users)
        flash("Registered Sucessfully 🎉 Redirecting to login...", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

# ------------- PROFILE --------------- #
@app.route("/profile", methods=["GET","POST"])
def profile():
    if not current_user():
        return redirect(url_for("login"))

    users = load_json(USERS_FILE)
    user = next(u for u in users if u["username"] == current_user())

    if request.method == "POST":
        user["bio"] = request.form.get("bio","")
        user["dob"] = request.form.get("dob","")

        avatar_file = request.files.get("avatar_file")
        if avatar_file and avatar_file.filename:
            avatar_path = DATA / "avatars"
            avatar_path.mkdir(exist_ok=True)
            filename = f"{user['username']}_{avatar_file.filename}"
            avatar_file.save(avatar_path / filename)
            user["avatar"] = filename

        if "quests" not in user:
            user["quests"] = {}
        user["quests"]["edit_profile"] = True

        save_json(USERS_FILE, users)
        flash("Profile updated!")

    return render_template("profile.html", user=user)

# --------------- SCHEDULE ------------ #
@app.route("/schedule")
def schedule():
    if not current_user():
        return redirect(url_for("login"))
    return render_template("schedule.html", events=get_user_events(current_user()))

@app.route("/schedule/add", methods=["POST"])
def add_schedule():
    if not current_user():
        return redirect(url_for("login"))

    events = load_json(SCHEDULE_FILE)

    events.append({
        "id": max([e["id"] for e in events], default=0) + 1,
        "owner": current_user(),
        "title": request.form["title"],
        "details": request.form.get("details",""),
        "time": request.form["time"],
        "created": today_str()
    })

    save_json(SCHEDULE_FILE, events)

    users = load_users()
    user = next(u for u in users if u ["username"] == current_user())
    if "quests" in user:
        user["quest"]["add_event"] = True
        save_users(users)

    return redirect(url_for("schedule"))

@app.route("/schedule/delete/<int:event_id>")
def delete_schedule(event_id):
    if not current_user():
        return redirect(url_for("login"))

    events = [e for e in load_json(SCHEDULE_FILE)
                if not (e["id"] == event_id and e["owner"] == current_user())]
    save_json(SCHEDULE_FILE, events)
    return redirect(url_for("schedule"))

# ---------------- NOTIFICATIONS --------------- #
@app.route("/notifications")
def notifications_api():
    if not current_user():
        return jsonify(ok=True, notifications=[], count=0)

    session["checked_notifications"] = True
    notifs = compute_notifications(current_user())
    count = notification_count(current_user())
    return jsonify(ok=True, notifications=notifs, count=count) 

@app.route("/notifications_page")
def notifications_page():
    if not current_user():
        return redirect(url_for("login"))

    session["checked_notifications"] = True
    notifs = compute_notifications(current_user())
    return render_template("notifications.html", notifications=notifs)

# ------------ DARK MODE --------------- #
@app.route("/toggle-dark", methods=["POST"])
def toggle_dark():
    if not current_user():
        flash("You must be logged in.", "warning")

    session["darkmode"] = not session.get("darkmode", False)
    users = load_json(USERS_FILE)
    user = next((u for u in users if u["username"] == current_user()), None)

    if user:
        if "quest" not in user:
            user["quests"] = {}
        user["quests"]["use_darkmode"] = True
        save_json(USERS_FILE, users)

    return redirect(request.referrer or url_for("index"))

# --------------- DAILY QUEST TOGGLE -------------#
@app.route("/quest/toggle/<quest_id>", methods=["POST"])
def toggle_quest(quest_id):
    if not current_user():
        return redirect(url_for("login"))

    users = load_json(USERS_FILE)
    user = next(u for u in users if u["username"] == current_user())

    if "quests" not in user:
        user["quests"] = {}

    user["quests"][quest_id] = not user["quests"].get(quest_id, False)
    save_json(USERS_FILE, users)

    return redirect(request.referrer or url_for("index"))

def get_user_quests(username):
    users = load_json(USERS_FILE)
    user = next(u for u in users if u["username"] == username)
    return user.get("quests", {})

if __name__ == "__main__":
    app.run(debug=True)