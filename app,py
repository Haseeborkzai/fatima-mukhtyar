"""
Smart Study Planner & Exam Preparation Assistant
Sections: 1 Settings | 2 Validation | 3 Database | 4 Reports | 5 AI | 6 UI
Logic is separate from the UI so test_app.py can test it without Streamlit.
Run:  streamlit run app.py
"""
from __future__ import annotations

import hashlib, hmac, html, os, secrets, sqlite3, time
from contextlib import contextmanager
from datetime import date, datetime, timedelta

import pandas as pd

# ---------------- 1. SETTINGS ----------------
DB_PATH = os.environ.get("STUDY_DB_PATH", "study_planner.db")
DEFAULT_MODEL = "gemini-2.5-flash"
PRIORITIES = ("Low", "Medium", "High")
STATUSES = ("Pending", "In Progress", "Done")
MAX_TITLE, MAX_TEXT, MAX_MINUTES = 100, 500, 1440
URGENT_DAYS = 7
AI_COOLDOWN = 5
PBKDF2_ROUNDS = 200_000

TIPS = [
    "Study in short focused blocks (25 min) with 5 min breaks.",
    "Small progress every day beats one big last-minute effort.",
    "Missed a task? No problem. Pick one small task and restart. You can do it!",
    "Explaining a topic in your own words is the best test of understanding.",
    "Sleep well. A rested brain remembers more.",
    "Start with the hardest subject when your energy is highest.",
    "Be proud of every step you took today, however small.",
]


def daily_tip(day: date | None = None) -> str:
    return TIPS[(day or date.today()).toordinal() % len(TIPS)]


# ---------------- 2. VALIDATION ----------------
class ValidationError(ValueError): ...
class AuthError(Exception): ...
class AIError(Exception): ...


def clean(text, max_len, field, required=True) -> str:
    text = "".join(c if c.isprintable() else " " for c in (text or "")).strip()
    if required and not text:
        raise ValidationError(f"{field} cannot be empty.")
    if len(text) > max_len:
        raise ValidationError(f"{field} must be at most {max_len} characters.")
    return text


def validate_username(u):
    u = (u or "").strip().lower()
    if not (3 <= len(u) <= 20 and all(c.isascii() and (c.isalnum() or c == "_") for c in u)):
        raise ValidationError("Username: 3-20 letters, numbers or underscore.")
    return u


def validate_pin(pin):
    if not (isinstance(pin, str) and pin.isascii() and pin.isdigit() and 4 <= len(pin) <= 8):
        raise ValidationError("PIN must be 4-8 digits.")
    return pin


def validate_date(d) -> date:
    if isinstance(d, datetime):
        d = d.date()
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d)
        except ValueError:
            raise ValidationError("Invalid date.")
    if not isinstance(d, date) or not (date(2000, 1, 1) <= d <= date(2100, 12, 31)):
        raise ValidationError("Invalid date.")
    return d


def validate_minutes(m) -> int:
    try:
        if isinstance(m, bool) or int(m) != float(m):
            raise ValueError
        m = int(m)
    except (TypeError, ValueError):
        raise ValidationError("Minutes must be a whole number.")
    if not 1 <= m <= MAX_MINUTES:
        raise ValidationError(f"Minutes must be between 1 and {MAX_MINUTES}.")
    return m


def validate_choice(v, options, field):
    if v not in options:
        raise ValidationError(f"Invalid {field}.")
    return v


# ---------------- 3. DATABASE ----------------
@contextmanager
def get_conn(db=DB_PATH):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db=DB_PATH):
    with get_conn(db) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL, salt BLOB NOT NULL, pin_hash BLOB NOT NULL,
            fails INTEGER NOT NULL DEFAULT 0, locked_until REAL NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS subjects(id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL, UNIQUE(user_id, name));
        CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
            title TEXT NOT NULL, due_date TEXT NOT NULL, priority TEXT NOT NULL, status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
            day TEXT NOT NULL, minutes INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS exams(id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL, exam_date TEXT NOT NULL);
        """)


def _hash(pin, salt):
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, PBKDF2_ROUNDS)


def create_user(username, pin, db=DB_PATH) -> int:
    username, pin = validate_username(username), validate_pin(pin)
    salt = secrets.token_bytes(16)
    try:
        with get_conn(db) as c:
            return c.execute("INSERT INTO users(username,salt,pin_hash) VALUES(?,?,?)",
                             (username, salt, _hash(pin, salt))).lastrowid
    except sqlite3.IntegrityError:
        raise ValidationError("Username already taken.")


def authenticate(username, pin, db=DB_PATH) -> int:
    err = AuthError("Wrong username or PIN.")
    with get_conn(db) as c:
        row = c.execute("SELECT * FROM users WHERE username=?",
                        ((username or "").strip().lower(),)).fetchone()
        if row is None:
            raise err
        if row["locked_until"] > time.time():
            raise AuthError("Too many attempts. Try again in a few minutes.")
        if hmac.compare_digest(_hash(pin or "", row["salt"]), row["pin_hash"]):
            c.execute("UPDATE users SET fails=0, locked_until=0 WHERE id=?", (row["id"],))
            return row["id"]
        fails = row["fails"] + 1
        lock = time.time() + 300 if fails >= 5 else 0
        c.execute("UPDATE users SET fails=?, locked_until=? WHERE id=?",
                  (0 if lock else fails, lock, row["id"]))
    raise err


def add_subject(uid, name, db=DB_PATH) -> int:
    name = clean(name, 50, "Subject name")
    try:
        with get_conn(db) as c:
            return c.execute("INSERT INTO subjects(user_id,name) VALUES(?,?)", (uid, name)).lastrowid
    except sqlite3.IntegrityError:
        raise ValidationError("You already have this subject.")


def list_subjects(uid, db=DB_PATH) -> pd.DataFrame:
    with get_conn(db) as c:
        rows = c.execute("SELECT id,name FROM subjects WHERE user_id=? ORDER BY name", (uid,)).fetchall()
    return pd.DataFrame([dict(r) for r in rows], columns=["id", "name"])


def _own_subject(c, uid, sid):
    if c.execute("SELECT 1 FROM subjects WHERE id=? AND user_id=?", (sid, uid)).fetchone() is None:
        raise ValidationError("Subject not found.")


def add_task(uid, subject_id, title, due, priority="Medium", status="Pending", db=DB_PATH) -> int:
    title = clean(title, MAX_TITLE, "Task title")
    due = validate_date(due)
    validate_choice(priority, PRIORITIES, "priority")
    validate_choice(status, STATUSES, "status")
    with get_conn(db) as c:
        _own_subject(c, uid, subject_id)
        return c.execute("INSERT INTO tasks(user_id,subject_id,title,due_date,priority,status) "
                         "VALUES(?,?,?,?,?,?)",
                         (uid, subject_id, title, due.isoformat(), priority, status)).lastrowid


def update_task_status(uid, task_id, status, db=DB_PATH):
    validate_choice(status, STATUSES, "status")
    with get_conn(db) as c:
        if c.execute("UPDATE tasks SET status=? WHERE id=? AND user_id=?",
                     (status, task_id, uid)).rowcount == 0:
            raise ValidationError("Task not found.")


def delete_task(uid, task_id, db=DB_PATH):
    with get_conn(db) as c:
        c.execute("DELETE FROM tasks WHERE id=? AND user_id=?", (task_id, uid))


def list_tasks(uid, db=DB_PATH) -> pd.DataFrame:
    with get_conn(db) as c:
        rows = c.execute("""SELECT t.id,s.name AS subject,t.title,t.due_date,t.priority,t.status
            FROM tasks t JOIN subjects s ON s.id=t.subject_id WHERE t.user_id=?
            ORDER BY t.due_date""", (uid,)).fetchall()
    df = pd.DataFrame([dict(r) for r in rows],
                      columns=["id", "subject", "title", "due_date", "priority", "status"])
    df["due_date"] = pd.to_datetime(df["due_date"]).dt.date
    return df


def log_session(uid, subject_id, day, minutes, db=DB_PATH) -> int:
    day, minutes = validate_date(day), validate_minutes(minutes)
    with get_conn(db) as c:
        _own_subject(c, uid, subject_id)
        return c.execute("INSERT INTO sessions(user_id,subject_id,day,minutes) VALUES(?,?,?,?)",
                         (uid, subject_id, day.isoformat(), minutes)).lastrowid


def list_sessions(uid, db=DB_PATH) -> pd.DataFrame:
    with get_conn(db) as c:
        rows = c.execute("""SELECT x.day,s.name AS subject,x.minutes FROM sessions x
            JOIN subjects s ON s.id=x.subject_id WHERE x.user_id=? ORDER BY x.day""", (uid,)).fetchall()
    df = pd.DataFrame([dict(r) for r in rows], columns=["day", "subject", "minutes"])
    df["day"] = pd.to_datetime(df["day"]).dt.date
    return df


def add_exam(uid, name, exam_date, db=DB_PATH) -> int:
    name, d = clean(name, MAX_TITLE, "Exam name"), validate_date(exam_date)
    with get_conn(db) as c:
        return c.execute("INSERT INTO exams(user_id,name,exam_date) VALUES(?,?,?)",
                         (uid, name, d.isoformat())).lastrowid


def delete_exam(uid, exam_id, db=DB_PATH):
    with get_conn(db) as c:
        c.execute("DELETE FROM exams WHERE id=? AND user_id=?", (exam_id, uid))


def list_exams(uid, today=None, db=DB_PATH) -> pd.DataFrame:
    """Upcoming exams (today or later) with days_left and urgent flag."""
    today = today or date.today()
    with get_conn(db) as c:
        rows = c.execute("SELECT id,name,exam_date FROM exams WHERE user_id=? AND exam_date>=? "
                         "ORDER BY exam_date", (uid, today.isoformat())).fetchall()
    df = pd.DataFrame([dict(r) for r in rows], columns=["id", "name", "exam_date"])
    df["exam_date"] = pd.to_datetime(df["exam_date"]).dt.date
    df["days_left"] = df["exam_date"].map(lambda d: days_remaining(d, today))
    df["urgent"] = df["days_left"] < URGENT_DAYS
    return df


# ---------------- 4. REPORTS ----------------
def days_remaining(exam_date, today=None) -> int:
    return (exam_date - (today or date.today())).days


def today_tasks(tasks: pd.DataFrame, today=None) -> pd.DataFrame:
    return tasks[tasks["due_date"] == (today or date.today())]


def completion(tasks: pd.DataFrame) -> tuple[int, int, float]:
    """(done, total, fraction 0..1)."""
    total = len(tasks)
    done = int((tasks["status"] == "Done").sum()) if total else 0
    return done, total, (done / total if total else 0.0)


def minutes_per_day(sessions: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    days = pd.date_range(start, end).date
    out = pd.DataFrame({"day": days})
    totals = sessions.groupby("day")["minutes"].sum() if not sessions.empty else {}
    out["minutes"] = out["day"].map(totals).fillna(0).astype(int)
    return out


def minutes_per_subject(sessions: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    if sessions.empty:
        return pd.DataFrame({"subject": [], "minutes": []})
    sub = sessions[(sessions["day"] >= start) & (sessions["day"] <= end)]
    return sub.groupby("subject", as_index=False)["minutes"].sum().sort_values("minutes", ascending=False)


def week_total(sessions, today=None) -> int:
    today = today or date.today()
    return int(minutes_per_day(sessions, today - timedelta(days=6), today)["minutes"].sum())


def fmt_minutes(m: int) -> str:
    return f"{m // 60}h {m % 60}m"


# ---------------- 5. AI (Gemini Flash) ----------------
MODES = {
    "Explain simply": "Explain this topic in simple language for a student, with one example: ",
    "Short summary": "Write a short summary (max 8 bullet points) of: ",
    "Practice questions": "Create 5 practice questions (with answers at the end) about: ",
    "Revision plan": "Suggest a realistic revision plan (day by day, max 7 days) for: ",
}
SYSTEM_PROMPT = ("You are a friendly study assistant for students. Be accurate and clear. "
                 "If unsure, say so; never invent facts, formulas or references. "
                 "Be encouraging, never judgemental. Keep answers concise. "
                 "Reply in the user's language. Decline non-study topics politely.")
AI_DISCLAIMER = ("🤖 AI-generated. It may contain mistakes. Please verify important facts "
                 "with your textbook or teacher.")


def get_api_key():
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    try:
        import streamlit as st
        return st.secrets.get("GEMINI_API_KEY")
    except Exception:
        return None


def ask_gemini(mode, topic, api_key=None, client=None, model=None) -> str:
    validate_choice(mode, tuple(MODES), "mode")
    topic = clean(topic, MAX_TEXT, "Topic")
    if client is None:
        if not api_key:
            raise AIError("AI is not set up yet (missing GEMINI_API_KEY).")
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
        except Exception:
            raise AIError("Could not start the AI service.")
    try:
        r = client.models.generate_content(
            model=model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL),
            contents=MODES[mode] + topic,
            config={"system_instruction": SYSTEM_PROMPT, "temperature": 0.4,
                    "max_output_tokens": 1200})
        text = (getattr(r, "text", None) or "").strip()
    except Exception as e:
        m = str(e).lower()
        if any(k in m for k in ("429", "quota", "rate", "exhausted")):
            raise AIError("AI is busy or the free limit is reached. Try again later.")
        if any(k in m for k in ("api key", "401", "403", "permission")):
            raise AIError("The AI service rejected the API key.")
        raise AIError("The AI service had a problem. Please try again later.")
    if not text:
        raise AIError("No answer received. Please rephrase your topic.")
    return text


# ---------------- 6. UI ----------------
CSS = """<style>
.block-container{max-width:860px;padding-top:1rem}
.hero{background:linear-gradient(135deg,#6a5acd,#ff7eb3);color:#fff;border-radius:18px;padding:18px 20px;margin-bottom:12px}
.hero h1{margin:0;font-size:1.5rem;color:#fff}.hero p{margin:4px 0 0;opacity:.95}
.tip{background:rgba(255,193,7,.15);border-left:5px solid #ffc107;border-radius:12px;padding:12px 14px;margin:8px 0 14px}
.exam{border-radius:12px;padding:10px 14px;margin-bottom:8px;border:1px solid rgba(128,128,128,.3)}
.exam.urgent{border-color:#ff5252;background:rgba(255,82,82,.1)}
</style>"""


def main():  # pragma: no cover - UI, run with streamlit
    import plotly.express as px
    import streamlit as st

    st.set_page_config(page_title="Smart Study Planner", page_icon="📚", layout="centered")
    st.markdown(CSS, unsafe_allow_html=True)
    init_db()
    st.markdown('<div class="hero"><h1>📚 Smart Study Planner</h1>'
                '<p>Plan. Study. Track. Ace your exams.</p></div>', unsafe_allow_html=True)

    if "uid" not in st.session_state:
        t1, t2 = st.tabs(["Log in", "Create account"])
        with t1, st.form("login"):
            u, p = st.text_input("Username"), st.text_input("PIN", type="password")
            if st.form_submit_button("Log in", use_container_width=True):
                try:
                    st.session_state.update(uid=authenticate(u, p), user=u.strip().lower())
                    st.rerun()
                except AuthError as e:
                    st.error(str(e))
        with t2, st.form("signup"):
            u = st.text_input("Choose username")
            p = st.text_input("Choose PIN (4-8 digits)", type="password")
            if st.form_submit_button("Create account", use_container_width=True):
                try:
                    st.session_state.update(uid=create_user(u, p), user=u.strip().lower())
                    st.rerun()
                except ValidationError as e:
                    st.error(str(e))
        st.markdown(f'<div class="tip">💡 {html.escape(daily_tip())}</div>', unsafe_allow_html=True)
        return

    uid, today = st.session_state["uid"], date.today()
    a, b = st.columns([3, 1])
    a.write(f"Hello **{html.escape(st.session_state['user'])}** 👋")
    if b.button("Log out", use_container_width=True):
        st.session_state.clear()
        st.rerun()
    st.markdown(f'<div class="tip">💡 {html.escape(daily_tip())}</div>', unsafe_allow_html=True)

    subjects, tasks = list_subjects(uid), list_tasks(uid)
    sessions, exams = list_sessions(uid), list_exams(uid)
    sub_map = dict(zip(subjects["name"], subjects["id"]))

    tabs = st.tabs(["🏠 Today", "✅ Tasks", "⏱️ Study time", "📊 Reports", "🎯 Exams", "🤖 AI helper"])

    with tabs[0]:
        tt = today_tasks(tasks)
        done, total, frac = completion(tt)
        st.progress(frac, text=f"{done} of {total} tasks done today")
        if total == 0:
            st.caption("No tasks due today. Add one in the Tasks tab or enjoy a rest! 🌤️")
        for _, r in tt.iterrows():
            st.write(f"**{r['title']}** · {r['subject']} · {r['priority']} · {r['status']}")
        late = tasks[(tasks["due_date"] < today) & (tasks["status"] != "Done")]
        if not late.empty:
            st.info(f"🌱 {len(late)} earlier task(s) are waiting. Pick one small one and restart. You've got this!")
        st.subheader("Upcoming exams")
        for _, e in exams.head(3).iterrows():
            st.markdown(f'<div class="exam {"urgent" if e["urgent"] else ""}">'
                        f'{"⚠️" if e["urgent"] else "📅"} <b>{html.escape(e["name"])}</b> · '
                        f'{e["days_left"]} day(s) left</div>', unsafe_allow_html=True)
        st.metric("Studied this week", fmt_minutes(week_total(sessions)))

    with tabs[1]:
        with st.expander("➕ Add subject"):
            with st.form("sub"):
                n = st.text_input("Subject name")
                if st.form_submit_button("Add subject"):
                    try:
                        add_subject(uid, n); st.rerun()
                    except ValidationError as e:
                        st.error(str(e))
        if not sub_map:
            st.info("Add your first subject to begin.")
        else:
            with st.form("task"):
                s = st.selectbox("Subject", list(sub_map))
                t = st.text_input("Task title")
                d = st.date_input("Due date", today)
                p = st.selectbox("Priority", PRIORITIES, index=1)
                if st.form_submit_button("Add task", use_container_width=True):
                    try:
                        add_task(uid, sub_map[s], t, d, p); st.rerun()
                    except ValidationError as e:
                        st.error(str(e))
        for _, r in tasks.iterrows():
            c1, c2, c3 = st.columns([4, 2, 1])
            c1.write(f"**{r['title']}** · {r['subject']} · due {r['due_date']} · {r['priority']}")
            ns = c2.selectbox("Status", STATUSES, index=STATUSES.index(r["status"]),
                              key=f"st{r['id']}", label_visibility="collapsed")
            if ns != r["status"]:
                update_task_status(uid, int(r["id"]), ns); st.rerun()
            if c3.button("🗑️", key=f"dt{r['id']}"):
                delete_task(uid, int(r["id"])); st.rerun()

    with tabs[2]:
        if not sub_map:
            st.info("Add a subject first (Tasks tab).")
        else:
            with st.form("sess"):
                s = st.selectbox("Subject", list(sub_map), key="ss")
                d = st.date_input("Date", today, max_value=today, key="sd")
                m = st.number_input("Minutes studied", 1, MAX_MINUTES, 30, step=5)
                if st.form_submit_button("Log session", use_container_width=True):
                    try:
                        log_session(uid, sub_map[s], d, m); st.success("Saved! Great work 🎉"); st.rerun()
                    except ValidationError as e:
                        st.error(str(e))
        st.write(f"**Today:** {fmt_minutes(int(minutes_per_day(sessions, today, today)['minutes'].sum()))}  |  "
                 f"**This week:** {fmt_minutes(week_total(sessions))}")

    with tabs[3]:
        d7 = minutes_per_day(sessions, today - timedelta(days=6), today)
        d30 = minutes_per_day(sessions, today - timedelta(days=29), today)
        st.plotly_chart(px.bar(d7, x="day", y="minutes", title="Study minutes: last 7 days",
                               color_discrete_sequence=["#6a5acd"]), use_container_width=True)
        st.plotly_chart(px.area(d30, x="day", y="minutes", title="Last 30 days",
                                color_discrete_sequence=["#ff7eb3"]), use_container_width=True)
        ps = minutes_per_subject(sessions, today - timedelta(days=29), today)
        if not ps.empty:
            st.plotly_chart(px.pie(ps, names="subject", values="minutes",
                                   title="Time per subject (30 days)"), use_container_width=True)
        done, total, frac = completion(tasks)
        st.metric("Overall task completion", f"{frac * 100:.0f}%", f"{done}/{total} tasks")
        if total:
            st.plotly_chart(px.histogram(tasks, x="status", color="status",
                                         title="Tasks by status"), use_container_width=True)

    with tabs[4]:
        with st.form("exam"):
            n, d = st.text_input("Exam name"), st.date_input("Exam date", today + timedelta(days=14))
            if st.form_submit_button("Add exam", use_container_width=True):
                try:
                    add_exam(uid, n, d); st.rerun()
                except ValidationError as e:
                    st.error(str(e))
        for _, e in exams.iterrows():
            c1, c2 = st.columns([5, 1])
            c1.markdown(f'<div class="exam {"urgent" if e["urgent"] else ""}">'
                        f'{"⚠️" if e["urgent"] else "📅"} <b>{html.escape(e["name"])}</b> · '
                        f'{e["exam_date"]} · <b>{e["days_left"]} day(s) left</b></div>',
                        unsafe_allow_html=True)
            if c2.button("🗑️", key=f"de{e['id']}"):
                delete_exam(uid, int(e["id"])); st.rerun()

    with tabs[5]:
        with st.form("ai"):
            mode = st.selectbox("What do you need?", list(MODES))
            topic = st.text_area("Topic", max_chars=MAX_TEXT, placeholder="e.g. Newton's second law")
            go = st.form_submit_button("Ask AI", use_container_width=True)
        if go:
            if time.time() - st.session_state.get("last_ai", 0) < AI_COOLDOWN:
                st.warning("Please wait a few seconds before asking again.")
            else:
                st.session_state["last_ai"] = time.time()
                try:
                    with st.spinner("Thinking..."):
                        ans = ask_gemini(mode, topic, api_key=get_api_key())
                    st.markdown(ans)
                    st.warning(AI_DISCLAIMER)
                except (ValidationError, AIError) as e:
                    st.error(str(e))


if __name__ == "__main__":
    main()
