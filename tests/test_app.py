"""Automated test cases. Test names match the Test Case IDs in Testing_Document_Group07.xlsx.  Run: python -m unittest -v"""
import io, os, shutil, tempfile, unittest
from datetime import datetime, timedelta
from openpyxl import Workbook, load_workbook
import seed
from app import create_app
from database import query, execute, FMT

class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = create_app({"DATABASE": os.path.join(self.tmp, "t.db"), "UPLOAD_DIR": self.tmp, "TESTING": True, "RATE_LIMIT": 1000})
        seed.seed(self.app); self.c = self.app.test_client()
    def tearDown(self): shutil.rmtree(self.tmp, ignore_errors=True)

    def token(self, c):
        with c.session_transaction() as s: t = s.get("csrf")
        if not t: c.get("/login")
        with c.session_transaction() as s: return s["csrf"]
    def post(self, url, data=None, c=None, follow=True):
        c = c or self.c; d = dict(data or {}); d["csrf_token"] = self.token(c)
        return c.post(url, data=d, follow_redirects=follow)
    def as_user(self, u, p="123456"):
        c = self.app.test_client(); self.post("/login", {"username": u, "password": p}, c); return c
    def txt(self, r): return r.get_data(as_text=True)
    def q(self, sql, args=()):
        with self.app.app_context(): return [dict(r) for r in query(sql, args)]
    def x(self, sql, args=()):
        with self.app.app_context(): execute(sql, args)
    def uid(self, username): return self.q("SELECT user_id FROM users WHERE username=?", (username,))[0]["user_id"]
    def csid(self, offset=0):
        return self.q("SELECT class_session_id FROM class_sessions ORDER BY session_date")[1 + offset]["class_session_id"]   # [1] = today
    def open_qr(self, lec=None):
        lec = lec or self.as_user("lecturer01"); r = self.post(f"/lecturer/session/{self.csid()}/open", c=lec)
        return lec, self.q("SELECT * FROM attendance_sessions")[0]
    def xlsx(self, rows):
        wb = Workbook(); ws = wb.active; ws.append(["username", "full_name", "email", "student_code", "major"])
        for r in rows: ws.append(r)
        b = io.BytesIO(); wb.save(b); b.seek(0); return b

class TestAuth(Base):
    def test_TC01(self):
        r = self.post("/login", {"username": "student01", "password": "123456"}); self.assertIn("Today's classes", self.txt(r))
    def test_TC02(self): self.assertIn("Invalid username or password.", self.txt(self.post("/login", {"username": "student01", "password": "wrongpass"})))
    def test_TC03(self): self.assertIn("Invalid username or password.", self.txt(self.post("/login", {"username": "nobody", "password": "123456"})))
    def test_TC04(self): self.assertIn("Please enter your username and password.", self.txt(self.post("/login", {"username": "", "password": ""})))
    def test_TC05(self):
        self.x("UPDATE users SET is_locked=1 WHERE username='student01'")
        self.assertIn("Your account is locked.", self.txt(self.post("/login", {"username": "student01", "password": "123456"})))
    def test_TC06(self): self.assertIn("User Accounts", self.txt(self.as_user("admin", "admin123").get("/admin/")))
    def test_TC07(self): self.assertIn("Lecturer Dashboard", self.txt(self.as_user("lecturer01").get("/lecturer/")))
    def test_TC08(self):
        c = self.as_user("student01"); self.post("/logout", c=c)
        self.assertEqual(c.get("/student/").status_code, 302)
    def test_TC09(self):
        r = self.c.get("/student/"); self.assertEqual(r.status_code, 302); self.assertIn("/login", r.headers["Location"])
    def test_TC10(self): self.assertEqual(self.as_user("student01").get("/admin/").status_code, 403)
    def test_TC11(self):
        r = self.post("/forgot", {"email": "student01@uni.edu"}); self.assertIn("Reset Link Sent", self.txt(r))
        self.assertEqual(len(self.app.config["OUTBOX"]), 1)
    def test_TC12(self):
        r = self.post("/forgot", {"email": "ghost@uni.edu"}); self.assertIn("Reset Link Sent", self.txt(r))
        self.assertEqual(len(self.app.config.get("OUTBOX", [])), 0)
    def _reset_link(self):
        self.post("/forgot", {"email": "student01@uni.edu"}); return "/reset/" + self.app.config["OUTBOX"][0]["body"].rsplit("/reset/", 1)[1]
    def test_TC13(self):
        link = self._reset_link(); r = self.post(link, {"password": "newpass1", "confirm": "newpass1"})
        self.assertIn("Password updated", self.txt(r)); self.assertIn("Today's classes", self.txt(self.post("/login", {"username": "student01", "password": "newpass1"})))
    def test_TC14(self):
        link = self._reset_link(); self.post(link, {"password": "newpass1", "confirm": "newpass1"})
        self.assertIn("invalid or has expired", self.txt(self.post(link, {"password": "other123", "confirm": "other123"})))
    def test_TC15(self): self.assertIn("do not match", self.txt(self.post(self._reset_link(), {"password": "newpass1", "confirm": "different"})))
    def test_TC16(self):
        c = self.as_user("student01"); r = self.post("/password", {"old": "123456", "new": "abcdef1", "confirm": "abcdef1"}, c)
        self.assertIn("Password changed successfully.", self.txt(r))
    def test_TC17(self):
        c = self.as_user("student01"); self.assertIn("Current password is incorrect.", self.txt(self.post("/password", {"old": "bad", "new": "abcdef1", "confirm": "abcdef1"}, c)))
    def test_TC18(self):
        c = self.as_user("student01"); self.assertIn("Password must be at least 6 characters.", self.txt(self.post("/password", {"old": "123456", "new": "123", "confirm": "123"}, c)))
    def test_TC19(self):
        c = self.as_user("student01"); r = self.post("/profile", {"full_name": "New Name", "email": "new@uni.edu", "phone": "0912345678"}, c)
        self.assertIn("Profile updated.", self.txt(r)); self.assertEqual(self.q("SELECT full_name FROM users WHERE username='student01'")[0]["full_name"], "New Name")
    def test_TC20(self):
        c = self.as_user("student01"); self.assertIn("Invalid email address.", self.txt(self.post("/profile", {"full_name": "A", "email": "not-an-email", "phone": ""}, c)))
    def test_TC21(self):
        c = self.as_user("student01"); self.assertIn("Email already exists.", self.txt(self.post("/profile", {"full_name": "A", "email": "student02@uni.edu", "phone": ""}, c)))

class TestAdmin(Base):
    def setUp(self): super().setUp(); self.a = self.as_user("admin", "admin123")
    def new_user(self, **k):
        d = dict(role="STUDENT", username="student09", password="123456", code="SV009", major="SE", dob="", full_name="Student 9", email="s9@uni.edu", phone="")
        d.update(k); return self.post("/admin/users/new", d, self.a)
    def test_TC22(self):
        self.assertIn("Account created.", self.txt(self.new_user())); self.assertTrue(self.q("SELECT 1 FROM students WHERE student_code='SV009'"))
    def test_TC23(self): self.assertIn("Username already exists.", self.txt(self.new_user(username="student01")))
    def test_TC24(self):
        uid = self.uid("student01"); self.assertIn("Lock Account", self.txt(self.a.get(f"/admin/users/{uid}/lock")))
        self.assertIn("Account locked.", self.txt(self.post(f"/admin/users/{uid}/lock", c=self.a)))
        self.assertIn("Your account is locked.", self.txt(self.post("/login", {"username": "student01", "password": "123456"})))
    def test_TC25(self):
        uid = self.uid("student01"); self.post(f"/admin/users/{uid}/lock", c=self.a)
        self.assertIn("Account unlocked.", self.txt(self.post(f"/admin/users/{uid}/unlock", c=self.a)))
        self.assertIn("Today's classes", self.txt(self.post("/login", {"username": "student01", "password": "123456"})))
    def test_TC26(self):
        f = self.xlsx([["imp1", "Import One", "imp1@uni.edu", "SV101", "SE"], ["imp2", "Import Two", "imp2@uni.edu", "SV102", "SE"]])
        self.assertIn("Imported 2 student(s).", self.txt(self.post("/admin/users/import", {"file": (f, "s.xlsx")}, self.a)))
    def test_TC27(self):
        f = self.xlsx([["imp1", "Import One", "imp1@uni.edu", "SV101", "SE"], ["student01", "Dup", "dup@uni.edu", "SV102", "SE"]])
        t = self.txt(self.post("/admin/users/import", {"file": (f, "s.xlsx")}, self.a))
        self.assertIn("Imported 1 student(s).", t); self.assertIn("Row 3: Username already exists.", t)
    def test_TC28(self): self.assertIn("Please upload an .xlsx file.", self.txt(self.post("/admin/users/import", {"file": (io.BytesIO(b"x"), "s.txt")}, self.a)))
    def test_TC29(self):
        fid = self.q("SELECT faculty_id FROM faculties")[0]["faculty_id"]
        r = self.post("/admin/courses", {"kind": "course", "code": "DB101", "name": "Databases", "credits": "3", "total_sessions": "15", "faculty_id": fid}, self.a)
        self.assertIn("Saved.", self.txt(r)); self.assertTrue(self.q("SELECT 1 FROM courses WHERE course_code='DB101'"))
    def test_TC30(self):
        fid = self.q("SELECT faculty_id FROM faculties")[0]["faculty_id"]
        self.assertIn("Course code already exists.", self.txt(self.post("/admin/courses", {"kind": "course", "code": "SE101", "name": "X", "credits": "3", "total_sessions": "10", "faculty_id": fid}, self.a)))
    def test_TC31(self):
        r = self.post("/admin/courses", {"kind": "class", "code": "SE101.02", "name": "SE G2", "semester": "2026-1", "course_id": 1, "lecturer_id": self.uid("lecturer01")}, self.a)
        self.assertIn("Saved.", self.txt(r)); self.assertTrue(self.q("SELECT 1 FROM class_sections WHERE class_code='SE101.02'"))
    def test_TC32(self):
        self.new_user(); self.assertIn("Saved.", self.txt(self.post("/admin/classes/1", {"kind": "enroll", "student_code": "SV009"}, self.a)))
    def test_TC33(self): self.assertIn("Student is already enrolled in this class.", self.txt(self.post("/admin/classes/1", {"kind": "enroll", "student_code": "SV001"}, self.a)))
    def test_TC34(self): self.assertIn("End time must be after start time.", self.txt(self.post("/admin/classes/1", {"kind": "session", "date": "2026-12-01", "start": "10:00", "end": "09:00", "room": "A1"}, self.a)))
    def test_TC35(self):
        self.assertIn("Rules saved.", self.txt(self.post("/admin/rules", {"qr": "15", "late": "5", "max": "25"}, self.a)))
        self.assertEqual(self.q("SELECT qr_valid_minutes q, max_absent_rate m FROM attendance_rules WHERE is_active=1")[0], {"q": 15, "m": 25.0})
    def test_TC36(self): self.assertIn("Late threshold cannot exceed QR validity.", self.txt(self.post("/admin/rules", {"qr": "5", "late": "10", "max": "20"}, self.a)))
    def test_TC37(self): self.assertIn("Maximum absence rate must be between 0 and 100.", self.txt(self.post("/admin/rules", {"qr": "10", "late": "5", "max": "150"}, self.a)))
    def test_TC63(self): self.assertIn("Administrator accounts cannot be locked.", self.txt(self.post(f"/admin/users/{self.uid('admin')}/lock", c=self.a)))
    def test_TC62(self): self.assertIn("University Statistics", self.txt(self.a.get("/admin/stats?q=Student+1")))

class TestAttendance(Base):
    def test_TC38(self):
        lec, a = self.open_qr(); self.assertEqual(len(a["qr_token"]), 64); self.assertIn("Attendance Session (QR)", self.txt(lec.get(f"/lecturer/attendance/{a['att_session_id']}")))
    def scan(self, user, token):
        c = self.as_user(user); return self.txt(self.post("/student/scan", {"token": token}, c))
    def test_TC39(self):
        _, a = self.open_qr(); self.assertIn("Your status: Present.", self.scan("student01", a["qr_token"]))
    def test_TC40(self):
        _, a = self.open_qr(); self.x("UPDATE attendance_sessions SET opened_at=?", ((datetime.now() - timedelta(minutes=8)).strftime(FMT),))
        self.assertIn("Your status: Late.", self.scan("student01", a["qr_token"]))
    def test_TC41(self):
        _, a = self.open_qr(); self.x("UPDATE attendance_sessions SET expires_at=?", ((datetime.now() - timedelta(minutes=1)).strftime(FMT),))
        self.assertIn("This QR code has expired.", self.scan("student01", a["qr_token"]))
    def test_TC42(self): self.open_qr(); self.assertIn("Invalid QR code.", self.scan("student01", "0" * 64))
    def test_TC43(self):
        _, a = self.open_qr(); a2 = self.as_user("admin", "admin123")
        self.post("/admin/users/new", dict(role="STUDENT", username="outsider", password="123456", code="SV777", major="", dob="", full_name="Out", email="o@uni.edu", phone=""), a2)
        self.assertIn("You are not enrolled in this class.", self.scan("outsider", a["qr_token"]))
    def test_TC44(self):
        _, a = self.open_qr(); c = self.as_user("student01"); self.post("/student/scan", {"token": a["qr_token"]}, c)
        self.assertIn("You have already checked in for this session.", self.txt(self.post("/student/scan", {"token": a["qr_token"]}, c)))
    def test_TC45(self):
        lec, a = self.open_qr(); self.post(f"/lecturer/attendance/{a['att_session_id']}/close", c=lec)
        self.assertIn("This attendance session is closed.", self.scan("student01", a["qr_token"]))
    def test_TC46(self):
        lec, a = self.open_qr(); self.scan("student01", a["qr_token"])
        self.assertIn("Attendance closed. 4 student(s) marked absent.", self.txt(self.post(f"/lecturer/attendance/{a['att_session_id']}/close", c=lec)))
        self.assertEqual(len(self.q("SELECT 1 FROM attendance_records WHERE status='ABSENT'")), 4)
    def test_TC47(self):
        a = self.as_user("admin", "admin123")
        self.post("/admin/users/new", dict(role="LECTURER", username="lecturer02", password="123456", code="GV002", major="", dob="", full_name="Other Lec", email="l2@uni.edu", phone=""), a)
        l2 = self.as_user("lecturer02"); self.assertIn("You can only manage your own classes.", self.txt(self.post(f"/lecturer/session/{self.csid()}/open", c=l2)))
        self.assertEqual(l2.get("/lecturer/class/1").status_code, 403)

    def manual(self, status="PRESENT", reason="Late by bus", user="student01", off=0):
        lec = self.as_user("lecturer01"); u = self.uid(user)
        return lec, self.txt(self.post(f"/lecturer/manual/{self.csid(off)}", {f"status_{u}": status, f"reason_{u}": reason}, lec))
    def test_TC48(self):
        _, t = self.manual(); self.assertIn("1 record(s) updated.", t)
        self.assertEqual(self.q("SELECT old_status o, new_status n, reason r FROM attendance_edit_logs")[0], {"o": "NONE", "n": "PRESENT", "r": "Late by bus"})
    def test_TC49(self):
        _, t = self.manual(reason=""); self.assertIn("1 record(s) updated.", t)
        self.assertEqual(self.q("SELECT new_status n, reason r FROM attendance_edit_logs")[0], {"n": "PRESENT", "r": ""})
    def test_TC50(self):
        lec, _ = self.manual(); self.manual("LATE", "Checked again")
        self.assertEqual(self.q("SELECT old_status o, new_status n FROM attendance_edit_logs ORDER BY log_id DESC")[0], {"o": "PRESENT", "n": "LATE"})
    def absence(self, reason="Sick", fname=None):
        c = self.as_user("student01"); d = {"class_session_id": self.csid(), "reason": reason}
        if fname: d["attachment"] = (io.BytesIO(b"data"), fname)
        return c, self.txt(self.post("/student/absence", d, c))
    def test_TC51(self): self.assertIn("Absence request submitted.", self.absence(fname="note.pdf")[1]); self.assertEqual(len(self.q("SELECT 1 FROM absence_requests")), 1)
    def test_TC52(self): self.assertIn("A reason is required.", self.absence(reason="")[1])
    def test_TC53(self): self.assertIn("Attachment must be a PDF, PNG or JPG file.", self.absence(fname="virus.exe")[1])
    def test_TC54(self):
        c, _ = self.absence(); self.assertIn("You already have an active request for this session.", self.txt(self.post("/student/absence", {"class_session_id": self.csid(), "reason": "again"}, c)))
    def test_TC55(self):
        self.absence(); lec = self.as_user("lecturer01"); rid = self.q("SELECT request_id FROM absence_requests")[0]["request_id"]
        self.assertIn("Request approved.", self.txt(self.post(f"/lecturer/absences/{rid}/approve", c=lec)))
        self.assertEqual(self.q("SELECT status FROM attendance_records")[0]["status"], "EXCUSED")
    def test_TC56(self):
        self.absence(); lec = self.as_user("lecturer01"); rid = self.q("SELECT request_id FROM absence_requests")[0]["request_id"]
        self.assertIn("Request rejected.", self.txt(self.post(f"/lecturer/absences/{rid}/reject", c=lec)))
        self.assertEqual(self.q("SELECT COUNT(*) n FROM attendance_records")[0]["n"], 0)
    def test_TC57(self):
        self.manual("ABSENT", "No show"); t = self.txt(self.as_user("student01").get("/student/history"))
        self.assertIn("Absent", t); self.assertIn("10.0%", t)
    def test_TC58(self):
        for off in (-1, 0, 1): self.manual("ABSENT", "No show", off=off)
        t = self.txt(self.as_user("student01").get("/student/"))
        self.assertIn("Warning: your absence rate", t); self.assertIn("30.0%", t); self.assertEqual(len(self.q("SELECT 1 FROM attendance_alerts")), 1)
    def test_TC59(self):
        self.manual("PRESENT", "ok"); t = self.txt(self.as_user("lecturer01").get("/lecturer/report?q=SV001"))
        self.assertIn("Student 1", t); self.assertNotIn("Student 2", t)
    def test_TC60(self):
        r = self.as_user("lecturer01").get("/lecturer/report/export/xlsx"); ws = load_workbook(io.BytesIO(r.data)).active
        self.assertIn("spreadsheetml", r.mimetype); self.assertEqual(ws.max_row, 6)
    def test_TC61(self):
        r = self.as_user("lecturer01").get("/lecturer/report/export/pdf"); self.assertEqual(r.mimetype, "application/pdf"); self.assertTrue(r.data.startswith(b"%PDF"))
    def test_TC64(self):
        t = self.txt(self.as_user("student01").get("/student/courses")); self.assertIn("SE101.01", t); self.assertIn("Software Engineering", t)

class TestSecurity(Base):
    def test_TC65(self): self.assertEqual(self.c.post("/login", data={"username": "student01", "password": "123456"}).status_code, 400)
    def test_TC66(self): self.assertIn("Invalid username or password.", self.txt(self.post("/login", {"username": "' OR '1'='1", "password": "x"})))
    def test_TC67(self):
        c = self.as_user("student01"); self.post("/profile", {"full_name": "<script>alert(1)</script>", "email": "x@uni.edu", "phone": ""}, c)
        t = self.txt(c.get("/profile")); self.assertNotIn("<script>alert(1)</script>", t); self.assertIn("&lt;script&gt;", t)
    def test_TC68(self): self.assertEqual(self.as_user("student01").get("/lecturer/").status_code, 403)
    def test_TC69(self):
        app = create_app({"DATABASE": os.path.join(self.tmp, "r.db"), "UPLOAD_DIR": self.tmp, "TESTING": True, "RATE_LIMIT": 3}); c = app.test_client()
        codes = []
        for _ in range(5):
            c.get("/login")
            with c.session_transaction() as s: t = s["csrf"]
            codes.append(c.post("/login", data={"username": "ratey", "password": "x", "csrf_token": t}).status_code)
        self.assertEqual(codes[-1], 429)
    def test_TC70(self):
        self.assertIn("<h1>Login</h1>", self.txt(self.c.get("/login"))); self.assertIn("viewport", self.txt(self.c.get("/login")))
    def test_TC71(self): self.assertIn("Show password", self.txt(self.c.get("/login")))

if __name__ == "__main__": unittest.main()
