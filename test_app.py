"""Automated tests. Run:  python -m unittest -v   (or: pytest). No API key needed."""
import os, tempfile, unittest
from datetime import date, timedelta

import pandas as pd

import app

TODAY = date(2026, 11, 3)


class FakeClient:
    """Mocked Gemini client."""
    def __init__(self, text="Mocked answer", error=None):
        self.text, self.error, self.calls = text, error, []
        self.models = self

    def generate_content(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        return type("R", (), {"text": self.text})()


class Base(unittest.TestCase):
    def setUp(self):
        fd, self.db = tempfile.mkstemp(suffix=".db"); os.close(fd)
        app.init_db(self.db)
        self.uid = app.create_user("sara", "1234", self.db)
        self.sid = app.add_subject(self.uid, "Math", self.db)

    def tearDown(self):
        os.remove(self.db)


class TestValidation(unittest.TestCase):
    def test_username_pin(self):
        self.assertEqual(app.validate_username(" Ali_1 "), "ali_1")
        for bad in ("a", "bad name", "x" * 21, ""):
            with self.assertRaises(app.ValidationError): app.validate_username(bad)
        for bad in ("12", "abcd", "123456789", "12 4"):
            with self.assertRaises(app.ValidationError): app.validate_pin(bad)

    def test_text_dates_minutes(self):
        with self.assertRaises(app.ValidationError): app.clean("   ", 10, "T")
        with self.assertRaises(app.ValidationError): app.clean("x" * 11, 10, "T")
        self.assertEqual(app.clean("  hi ", 10, "T"), "hi")
        with self.assertRaises(app.ValidationError): app.validate_date("2026-13-45")
        with self.assertRaises(app.ValidationError): app.validate_date("abc")
        self.assertEqual(app.validate_date("2026-11-03"), TODAY)
        for bad in (0, -5, 1441, "abc", 2.5, True, None):
            with self.assertRaises(app.ValidationError): app.validate_minutes(bad)
        self.assertEqual(app.validate_minutes("45"), 45)


class TestAuth(Base):
    def test_login_and_hashing(self):
        self.assertEqual(app.authenticate("SARA", "1234", self.db), self.uid)
        with self.assertRaises(app.AuthError): app.authenticate("sara", "9999", self.db)
        with self.assertRaises(app.AuthError): app.authenticate("nobody", "1234", self.db)
        with app.get_conn(self.db) as c:
            h = c.execute("SELECT pin_hash FROM users").fetchone()[0]
        self.assertNotIn(b"1234", h)

    def test_duplicate_and_lockout(self):
        with self.assertRaises(app.ValidationError): app.create_user("sara", "5555", self.db)
        for _ in range(5):
            with self.assertRaises(app.AuthError): app.authenticate("sara", "0000", self.db)
        with self.assertRaises(app.AuthError) as cm: app.authenticate("sara", "1234", self.db)
        self.assertIn("Too many", str(cm.exception))


class TestTasks(Base):
    def test_add_update_progress(self):
        t1 = app.add_task(self.uid, self.sid, "Ch1", TODAY, "High", db=self.db)
        app.add_task(self.uid, self.sid, "Ch2", TODAY, db=self.db)
        app.add_task(self.uid, self.sid, "Later", TODAY + timedelta(days=2), db=self.db)
        tasks = app.list_tasks(self.uid, self.db)
        tt = app.today_tasks(tasks, TODAY)
        self.assertEqual(app.completion(tt), (0, 2, 0.0))
        app.update_task_status(self.uid, t1, "Done", self.db)
        done, total, frac = app.completion(app.today_tasks(app.list_tasks(self.uid, self.db), TODAY))
        self.assertEqual((done, total, frac), (1, 2, 0.5))
        self.assertEqual(app.completion(tasks.iloc[0:0]), (0, 0, 0.0))

    def test_invalid_and_isolation(self):
        for kw in ({"title": ""}, {"due": "bad"}, {"priority": "Urgent"}, {"status": "Nope"}):
            args = dict(title="x", due=TODAY, priority="Low", status="Pending"); args.update(kw)
            with self.assertRaises(app.ValidationError):
                app.add_task(self.uid, self.sid, args["title"], args["due"],
                             args["priority"], args["status"], self.db)
        other = app.create_user("omar", "4321", self.db)
        with self.assertRaises(app.ValidationError):  # other user's subject
            app.add_task(other, self.sid, "hack", TODAY, db=self.db)
        t = app.add_task(self.uid, self.sid, "mine", TODAY, db=self.db)
        with self.assertRaises(app.ValidationError): app.update_task_status(other, t, "Done", self.db)
        app.delete_task(other, t, self.db)
        self.assertEqual(len(app.list_tasks(self.uid, self.db)), 1)
        app.delete_task(self.uid, t, self.db)
        self.assertTrue(app.list_tasks(self.uid, self.db).empty)

    def test_sql_injection_is_stored_as_text(self):
        app.add_task(self.uid, self.sid, "x'); DROP TABLE tasks;--", TODAY, db=self.db)
        self.assertEqual(len(app.list_tasks(self.uid, self.db)), 1)

    def test_duplicate_subject(self):
        with self.assertRaises(app.ValidationError): app.add_subject(self.uid, "Math", self.db)


class TestStudyTime(Base):
    def test_totals(self):
        phys = app.add_subject(self.uid, "Physics", self.db)
        app.log_session(self.uid, self.sid, TODAY, 60, self.db)
        app.log_session(self.uid, self.sid, TODAY, 30, self.db)
        app.log_session(self.uid, phys, TODAY - timedelta(days=3), 45, self.db)
        app.log_session(self.uid, phys, TODAY - timedelta(days=20), 100, self.db)
        s = app.list_sessions(self.uid, self.db)
        d = app.minutes_per_day(s, TODAY - timedelta(days=6), TODAY)
        self.assertEqual(len(d), 7)
        self.assertEqual(int(d[d["day"] == TODAY]["minutes"].iloc[0]), 90)
        self.assertEqual(app.week_total(s, TODAY), 135)
        ps = app.minutes_per_subject(s, TODAY - timedelta(days=29), TODAY)
        self.assertEqual(dict(zip(ps["subject"], ps["minutes"])), {"Math": 90, "Physics": 145})
        self.assertEqual(app.fmt_minutes(135), "2h 15m")

    def test_empty_and_invalid(self):
        s = app.list_sessions(self.uid, self.db)
        self.assertEqual(app.week_total(s, TODAY), 0)
        self.assertTrue(app.minutes_per_subject(s, TODAY, TODAY).empty)
        with self.assertRaises(app.ValidationError): app.log_session(self.uid, self.sid, TODAY, -10, self.db)
        with self.assertRaises(app.ValidationError): app.log_session(self.uid, 999, TODAY, 10, self.db)


class TestExams(Base):
    def test_countdown_and_urgent(self):
        app.add_exam(self.uid, "Math final", TODAY + timedelta(days=3), self.db)
        app.add_exam(self.uid, "Physics", TODAY + timedelta(days=7), self.db)
        app.add_exam(self.uid, "Old exam", TODAY - timedelta(days=1), self.db)
        df = app.list_exams(self.uid, TODAY, self.db)
        self.assertEqual(list(df["name"]), ["Math final", "Physics"])  # past hidden, sorted
        self.assertEqual(list(df["days_left"]), [3, 7])
        self.assertEqual(list(df["urgent"]), [True, False])   # <7 days only
        self.assertEqual(app.days_remaining(TODAY, TODAY), 0)
        with self.assertRaises(app.ValidationError): app.add_exam(self.uid, "", TODAY, self.db)


class TestAI(unittest.TestCase):
    def test_success_and_prompt(self):
        fc = FakeClient("Newton explained")
        out = app.ask_gemini("Explain simply", "Newton's law", client=fc)
        self.assertEqual(out, "Newton explained")
        self.assertIn("Newton's law", fc.calls[0]["contents"])
        self.assertIn("system_instruction", fc.calls[0]["config"])

    def test_errors_are_friendly(self):
        cases = {"429 quota": "busy", "403 permission denied": "API key", "boom": "problem"}
        for raw, expected in cases.items():
            with self.assertRaises(app.AIError) as cm:
                app.ask_gemini("Short summary", "x", client=FakeClient(error=RuntimeError(raw)))
            self.assertIn(expected, str(cm.exception))
            self.assertNotIn(raw, str(cm.exception))
        with self.assertRaises(app.AIError): app.ask_gemini("Short summary", "x", client=FakeClient(""))
        with self.assertRaises(app.AIError): app.ask_gemini("Short summary", "x")  # no key
        with self.assertRaises(app.ValidationError): app.ask_gemini("Short summary", "  ", client=FakeClient())
        with self.assertRaises(app.ValidationError): app.ask_gemini("Hack mode", "x", client=FakeClient())
        with self.assertRaises(app.ValidationError): app.ask_gemini("Short summary", "x" * 501, client=FakeClient())

    def test_no_hardcoded_key(self):
        with open(app.__file__, encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("AIza", src)


class TestMisc(unittest.TestCase):
    def test_tip_stable_per_day(self):
        self.assertEqual(app.daily_tip(TODAY), app.daily_tip(TODAY))
        self.assertIn(app.daily_tip(TODAY + timedelta(days=1)), app.TIPS)


if __name__ == "__main__":
    unittest.main()
