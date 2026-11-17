"""Users: abstract User with Admin, Lecturer and Student (class diagram)."""
import hashlib, io, re, secrets
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from openpyxl import load_workbook
from werkzeug.security import generate_password_hash, check_password_hash
from database import query, execute, now, AppError, FMT
from mailer import send_mail
from models.academic import Faculty, Course, ClassSection, Session
from models.attendance import AttendanceRule, AttendanceSession, AttendanceRecord, AbsenceRequest
from models.report import Report

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def _check_email(email):
    if not EMAIL_RE.match((email or "").strip()): raise AppError("Invalid email address.")
    return email.strip().lower()

def _check_password(pw):
    if len(pw or "") < 6: raise AppError("Password must be at least 6 characters.")

class User(ABC):
    role = None
    def __init__(self, row):
        self.user_id, self.username, self.full_name = row["user_id"], row["username"], row["full_name"]
        self.email, self.phone, self.is_locked = row["email"], row["phone"], bool(row["is_locked"])

    @abstractmethod
    def home(self): """Endpoint of the role's dashboard."""

    @staticmethod
    def _from_row(row): return {"ADMIN": Admin, "LECTURER": Lecturer, "STUDENT": Student}[row["role"]](row)
    @staticmethod
    def get(user_id):
        row = query("SELECT * FROM users WHERE user_id=?", (user_id,), one=True)
        return User._from_row(row) if row else None

    @staticmethod
    def login(username, password):
        if not (username or "").strip() or not password: raise AppError("Please enter your username and password.")
        row = query("SELECT * FROM users WHERE username=?", (username.strip(),), one=True)
        if not row or not check_password_hash(row["password_hash"], password): raise AppError("Invalid username or password.")
        if row["is_locked"]: raise AppError("Your account is locked. Please contact the administrator.")
        execute("UPDATE users SET last_login_at=? WHERE user_id=?", (now(), row["user_id"]))
        return User._from_row(row)

    def logout(self): return None            # session is cleared by the controller

    def change_password(self, old, new, confirm):
        row = query("SELECT password_hash FROM users WHERE user_id=?", (self.user_id,), one=True)
        if not check_password_hash(row["password_hash"], old or ""): raise AppError("Current password is incorrect.")
        _check_password(new)
        if new != confirm: raise AppError("New password and confirmation do not match.")
        if new == old: raise AppError("New password must be different from the current password.")
        execute("UPDATE users SET password_hash=? WHERE user_id=?", (generate_password_hash(new), self.user_id))

    @staticmethod
    def request_reset(email, link_builder):
        """Always silent for unknown emails. Token is stored hashed, single-use, valid 30 minutes."""
        row = query("SELECT user_id FROM users WHERE email=?", ((email or "").strip().lower(),), one=True)
        if not row: return None
        raw = secrets.token_urlsafe(32)
        execute("INSERT INTO password_reset_tokens(user_id,token_hash,expires_at) VALUES(?,?,?)",
                (row["user_id"], hashlib.sha256(raw.encode()).hexdigest(), (datetime.now() + timedelta(minutes=30)).strftime(FMT)))
        send_mail(email.strip().lower(), "Password reset", "Reset your password (valid 30 minutes): " + link_builder(raw))
        return raw

    @staticmethod
    def reset_password(raw, new, confirm):
        h = hashlib.sha256((raw or "").encode()).hexdigest()
        t = query("SELECT * FROM password_reset_tokens WHERE token_hash=? AND used_at IS NULL AND expires_at>?", (h, now()), one=True)
        if not t: raise AppError("The reset link is invalid or has expired.")
        _check_password(new)
        if new != confirm: raise AppError("New password and confirmation do not match.")
        execute("UPDATE users SET password_hash=? WHERE user_id=?", (generate_password_hash(new), t["user_id"]))
        execute("UPDATE password_reset_tokens SET used_at=? WHERE token_id=?", (now(), t["token_id"]))

    @staticmethod
    def valid_reset_token(raw):
        h = hashlib.sha256((raw or "").encode()).hexdigest()
        return query("SELECT 1 FROM password_reset_tokens WHERE token_hash=? AND used_at IS NULL AND expires_at>?", (h, now()), one=True) is not None

    def update_profile(self, full_name, email, phone):
        if not (full_name or "").strip(): raise AppError("Full name is required.")
        email = _check_email(email)
        if phone and not re.fullmatch(r"\+?\d{8,15}", phone.strip()): raise AppError("Invalid phone number.")
        if query("SELECT 1 FROM users WHERE email=? AND user_id<>?", (email, self.user_id), one=True): raise AppError("Email already exists.")
        execute("UPDATE users SET full_name=?, email=?, phone=? WHERE user_id=?", (full_name.strip(), email, (phone or "").strip(), self.user_id))

class Admin(User):
    role = "ADMIN"
    def home(self): return "admin.users"

    def manage_accounts(self, role, username, password, full_name, email, phone="", code="", major="", dob=None):
        if role not in ("LECTURER", "STUDENT"): raise AppError("Role must be Lecturer or Student.")
        for k, v in (("Username", username), ("Full name", full_name), ("Code", code)):
            if not (v or "").strip(): raise AppError(f"{k} is required.")
        _check_password(password); email = _check_email(email)
        if query("SELECT 1 FROM users WHERE username=?", (username.strip(),), one=True): raise AppError("Username already exists.")
        if query("SELECT 1 FROM users WHERE email=?", (email,), one=True): raise AppError("Email already exists.")
        table, col = ("students", "student_code") if role == "STUDENT" else ("lecturers", "lecturer_code")
        if query(f"SELECT 1 FROM {table} WHERE {col}=?", (code.strip(),), one=True): raise AppError("Code already exists.")
        uid = execute("INSERT INTO users(username,password_hash,full_name,email,phone,role,is_locked,created_at) VALUES(?,?,?,?,?,?,0,?)",
                      (username.strip(), generate_password_hash(password), full_name.strip(), email, (phone or "").strip(), role, now()))
        if role == "STUDENT": execute("INSERT INTO students(user_id,student_code,date_of_birth,major) VALUES(?,?,?,?)", (uid, code.strip(), dob or None, major or ""))
        else: execute("INSERT INTO lecturers(user_id,lecturer_code) VALUES(?,?)", (uid, code.strip()))
        return uid

    def update_account(self, user_id, full_name, email, phone):
        u = User.get(user_id)
        if not u: raise AppError("User not found.")
        u.update_profile(full_name, email, phone)

    def set_locked(self, user_id, locked):
        u = User.get(user_id)
        if not u: raise AppError("User not found.")
        if u.role == "ADMIN": raise AppError("Administrator accounts cannot be locked.")
        execute("UPDATE users SET is_locked=? WHERE user_id=?", (1 if locked else 0, user_id))

    def import_students(self, file):
        """Excel columns: username | full_name | email | student_code | major (optional). Initial password = student code + "@123"."""
        if not file or not file.filename.lower().endswith(".xlsx"): raise AppError("Please upload an .xlsx file.")
        try: ws = load_workbook(io.BytesIO(file.read()), read_only=True).active
        except Exception: raise AppError("The file could not be read.")
        created, errors = 0, []
        for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row or not any(row): continue
            username, name, email, code, major = (list(row) + [None] * 5)[:5]
            try:
                self.manage_accounts("STUDENT", str(username or ""), f"{code}@123", str(name or ""), str(email or ""),
                                     code=str(code or ""), major=str(major or "")); created += 1
            except AppError as e: errors.append(f"Row {i}: {e}")
        return created, errors

    def manage_courses(self, code, name, credits, total_sessions, faculty_id): return Course.create(code, name, credits, total_sessions, faculty_id)
    def manage_classes(self, *a): return ClassSection.create(*a)
    def configure_rules(self, qr, late, mx): AttendanceRule.update(self.user_id, qr, late, mx)
    def view_statistics(self, **flt): return Report.filter(**flt)

class Lecturer(User):
    role = "LECTURER"
    def home(self): return "lecturer.dashboard"
    def open_session(self, class_session_id): return AttendanceSession.open(self.user_id, class_session_id)
    def close_session(self, att_id): return AttendanceSession.close(self.user_id, att_id)
    def mark_manually(self, class_session_id, student_id, status, reason): return AttendanceRecord.update_status(self.user_id, class_session_id, student_id, status, reason)
    edit_attendance = mark_manually
    def review_request(self, request_id, approve): return AbsenceRequest.review(self.user_id, request_id, approve)
    def export_report(self, fmt, **flt):
        rows = Report.filter(lecturer_id=self.user_id, **flt); Report.log(self.user_id, "attendance", fmt)
        return Report.export_excel(rows) if fmt == "xlsx" else Report.export_pdf(rows)
    def owns_class(self, class_id):
        c = ClassSection.get(class_id); return bool(c and c["lecturer_id"] == self.user_id)

class Student(User):
    role = "STUDENT"
    def home(self): return "student.dashboard"
    def scan_qr(self, token): return AttendanceRecord.check_in(self.user_id, token)
    def submit_absence_request(self, class_session_id, reason, file=None): return AbsenceRequest.submit(self.user_id, class_session_id, reason, file)
    def get_attendance_rate(self, class_id): return ClassSection.calculate_rate(class_id, self.user_id)
    def view_history(self, class_id=None):
        out = []
        for c in ClassSection.for_student(self.user_id):
            if class_id and c["class_id"] != class_id: continue
            rows = query("""SELECT x.session_date, x.start_time, x.room, r.status, r.method, r.check_in_time FROM class_sessions x
                LEFT JOIN attendance_sessions a USING(class_session_id)
                LEFT JOIN attendance_records r ON r.att_session_id=a.att_session_id AND r.student_id=?
                WHERE x.class_id=? ORDER BY x.session_date, x.start_time""", (self.user_id, c["class_id"]))
            out.append({"cls": c, "rows": rows, "rate": self.get_attendance_rate(c["class_id"])})
        return out
