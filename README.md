# 📚 Smart Study Planner & Exam Preparation Assistant

A Streamlit web app to organize subjects and tasks, log study time, count down to exams,
view reports and get AI study help (Google Gemini Flash).

## Features
1. Subjects and tasks (title, due date, priority Low/Medium/High, status Pending/In Progress/Done)
2. Daily dashboard with progress bar
3. Study time tracker (per day, per week, per subject)
4. Weekly/monthly interactive charts (Plotly)
5. Exam countdown (red highlight when fewer than 7 days left)
6. AI helper: explain simply, short summary, practice questions, revision plan (always labelled AI-generated)
7. Daily motivation tip (never shames missed tasks)
8. Private accounts: username + hashed PIN

## Libraries (what and why)
| Library | Purpose |
|---|---|
| streamlit | Builds the web UI using only Python |
| pandas | Tables, grouping and totals for reports |
| plotly | Interactive charts |
| google-genai | Official SDK to call Gemini |
| sqlite3 (built in) | Local database, no server needed |
| hashlib / hmac / secrets (built in) | PIN hashing (PBKDF2 + random salt) |
| unittest (built in) | Automated tests |

## Run locally
```bash
pip install -r requirements.txt
# Windows (PowerShell): $env:GEMINI_API_KEY="your_key"      Mac/Linux: export GEMINI_API_KEY="your_key"
streamlit run app.py
```
Get a free key at https://aistudio.google.com/apikey . The app works without a key; only the AI tab needs it.

## Run the tests (no API key needed, AI is mocked)
```bash
python -m unittest -v
```

## How the code works (for beginners)
`app.py` has 6 sections:
1. **Settings**: constants (priorities, limits, tips).
2. **Validation**: every input is checked (empty title, bad date, negative minutes, too long text, bad PIN).
3. **Database**: 5 tables (`users, subjects, tasks, sessions, exams`). Every query uses `?` placeholders (parameterized SQL), so SQL injection is not possible. Every row has `user_id`, so users only see their own data.
4. **Reports**: pure functions using pandas (progress %, minutes per day/subject, days remaining).
5. **AI**: builds a prompt, calls Gemini, turns any error into a friendly message. Key is read from environment or Streamlit Secrets, never from the code.
6. **UI**: `main()` draws tabs and calls the functions above. Logic is separate from UI, so tests run without Streamlit.

## Upload to GitHub (website only)
1. Go to github.com and sign in (or sign up).
2. Click **+** (top right) → **New repository**. Name: `smart-study-planner`. Choose **Public** (needed for free Streamlit deploy) → **Create repository**.
3. Click **uploading an existing file**.
4. Drag in: `app.py`, `requirements.txt`, `README.md`, `.gitignore`, `test_app.py`. (Do NOT upload any `.db` file or secrets.)
5. Click **Commit changes**.

## Deploy on Streamlit Community Cloud
1. Open https://share.streamlit.io and sign in with GitHub.
2. Click **Create app** → choose your repository, branch `main`, main file `app.py`.
3. Click **Advanced settings → Secrets** and paste:
   ```toml
   GEMINI_API_KEY = "paste_your_key_here"
   ```
4. Click **Deploy**. Wait a few minutes. You get a public link to share.
5. To change the key later: App menu → **Settings → Secrets**.

## Presentation outline (5-7 minutes)
1. Problem: students struggle to organize study and exams
2. Solution and demo: login → add subject/task → log time → charts → exam countdown → AI helper
3. Architecture: Streamlit UI ↔ Python logic ↔ SQLite; Gemini via API
4. Security: hashed PIN, parameterized SQL, input validation, secret key
5. Testing: 15 automated tests with mocked AI
6. Limitations and future work

## Likely viva questions
- **Why Streamlit?** Quick, pure-Python web apps without HTML/JS.
- **Why SQLite?** Built in, zero setup, perfect for small apps.
- **How is the PIN stored?** Never plain. PBKDF2-SHA256 with a random salt and 200,000 rounds; compared with `hmac.compare_digest`.
- **Why a salt?** So equal PINs give different hashes and rainbow tables fail.
- **What is SQL injection and how did you prevent it?** Attacker input changing a query; prevented by `?` placeholders. A test proves `DROP TABLE` text is stored harmlessly.
- **How do you protect the API key?** Environment variable or Streamlit Secrets; `.gitignore` excludes secrets.
- **Why separate logic from UI?** So it can be unit tested without a browser.
- **How did you test AI without a key?** A fake client object returns fixed text or raises errors.
- **How is days remaining computed?** `(exam_date - today).days`; urgent if less than 7.
- **Why can PIN be guessed?** A 4-digit PIN is weak, so accounts lock for 5 minutes after 5 wrong tries.

## Honest limitations
- **SQLite data may reset on Streamlit Cloud** (its disk is temporary; app restarts/redeploys can erase it). For permanent data use an external database (e.g. Supabase/Postgres) .
- A short PIN is weaker than a password; there is no PIN recovery or email reset.
- AI answers can be wrong; the app only reminds users to verify them.
- Free Gemini quota is limited; the app shows a friendly message when it runs out.
- The Streamlit UI was not auto-tested (no browser tests); only the logic is unit-tested.
- Free Streamlit apps go to sleep when unused.
