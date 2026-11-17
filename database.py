"""Data access helpers + relational schema (mirrors the ERD in the specification)."""
import sqlite3
from datetime import datetime
from flask import g, current_app

FMT = "%Y-%m-%d %H:%M:%S"
def now(): return datetime.now().strftime(FMT)
def parse(s): return datetime.strptime(s, FMT)

class AppError(Exception):
    """Business-rule violation; message is shown to the user."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
 password_hash TEXT NOT NULL, full_name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, phone TEXT DEFAULT '',
 role TEXT NOT NULL CHECK(role IN ('ADMIN','LECTURER','STUDENT')), is_locked INTEGER DEFAULT 0,
 created_at TEXT, last_login_at TEXT);
CREATE TABLE IF NOT EXISTS password_reset_tokens(token_id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER NOT NULL REFERENCES users, token_hash TEXT UNIQUE NOT NULL, expires_at TEXT NOT NULL, used_at TEXT);
CREATE TABLE IF NOT EXISTS notifications(notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER NOT NULL REFERENCES users, message TEXT NOT NULL, is_read INTEGER DEFAULT 0, created_at TEXT);
CREATE TABLE IF NOT EXISTS reports(report_id INTEGER PRIMARY KEY AUTOINCREMENT, generated_by INTEGER REFERENCES users,
 report_type TEXT, file_format TEXT, generated_at TEXT);
CREATE TABLE IF NOT EXISTS faculties(faculty_id INTEGER PRIMARY KEY AUTOINCREMENT, faculty_name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS courses(course_id INTEGER PRIMARY KEY AUTOINCREMENT, course_code TEXT UNIQUE NOT NULL,
 course_name TEXT NOT NULL, credits INTEGER NOT NULL, total_sessions INTEGER NOT NULL,
 faculty_id INTEGER NOT NULL REFERENCES faculties);
CREATE TABLE IF NOT EXISTS students(user_id INTEGER PRIMARY KEY REFERENCES users, student_code TEXT UNIQUE NOT NULL,
 date_of_birth TEXT, major TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS lecturers(user_id INTEGER PRIMARY KEY REFERENCES users, lecturer_code TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS class_sections(class_id INTEGER PRIMARY KEY AUTOINCREMENT, class_code TEXT UNIQUE NOT NULL,
 class_name TEXT NOT NULL, semester TEXT NOT NULL, course_id INTEGER NOT NULL REFERENCES courses,
 lecturer_id INTEGER NOT NULL REFERENCES lecturers);
CREATE TABLE IF NOT EXISTS class_sessions(class_session_id INTEGER PRIMARY KEY AUTOINCREMENT,
 class_id INTEGER NOT NULL REFERENCES class_sections, session_date TEXT NOT NULL, start_time TEXT NOT NULL,
 end_time TEXT NOT NULL, room TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS enrollments(enrollment_id INTEGER PRIMARY KEY AUTOINCREMENT,
 class_id INTEGER NOT NULL REFERENCES class_sections, student_id INTEGER NOT NULL REFERENCES students,
 enrolled_date TEXT, UNIQUE(class_id, student_id));
CREATE TABLE IF NOT EXISTS attendance_rules(rule_id INTEGER PRIMARY KEY AUTOINCREMENT, qr_valid_minutes INTEGER NOT NULL,
 late_threshold_minutes INTEGER NOT NULL, max_absent_rate REAL NOT NULL, is_active INTEGER DEFAULT 1,
 updated_by INTEGER REFERENCES users, updated_at TEXT);
CREATE TABLE IF NOT EXISTS attendance_sessions(att_session_id INTEGER PRIMARY KEY AUTOINCREMENT,
 class_session_id INTEGER UNIQUE NOT NULL REFERENCES class_sessions, opened_by INTEGER NOT NULL REFERENCES lecturers,
 qr_token TEXT UNIQUE NOT NULL, opened_at TEXT, expires_at TEXT, closed_at TEXT, is_open INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS attendance_records(record_id INTEGER PRIMARY KEY AUTOINCREMENT,
 att_session_id INTEGER NOT NULL REFERENCES attendance_sessions, student_id INTEGER NOT NULL REFERENCES students,
 status TEXT NOT NULL CHECK(status IN ('PRESENT','ABSENT','LATE','EXCUSED')), check_in_time TEXT,
 method TEXT NOT NULL CHECK(method IN ('QR','MANUAL')), note TEXT DEFAULT '', UNIQUE(att_session_id, student_id));
CREATE TABLE IF NOT EXISTS attendance_edit_logs(log_id INTEGER PRIMARY KEY AUTOINCREMENT,
 record_id INTEGER NOT NULL REFERENCES attendance_records, edited_by INTEGER NOT NULL REFERENCES users,
 old_status TEXT, new_status TEXT NOT NULL, reason TEXT NOT NULL, edited_at TEXT);
CREATE TABLE IF NOT EXISTS absence_requests(request_id INTEGER PRIMARY KEY AUTOINCREMENT,
 student_id INTEGER NOT NULL REFERENCES students, class_session_id INTEGER NOT NULL REFERENCES class_sessions,
 reviewed_by INTEGER REFERENCES users, reason TEXT NOT NULL, attachment_url TEXT DEFAULT '',
 status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','APPROVED','REJECTED')),
 submitted_at TEXT, processed_at TEXT);
CREATE TABLE IF NOT EXISTS attendance_alerts(notification_id INTEGER PRIMARY KEY REFERENCES notifications,
 enrollment_id INTEGER NOT NULL REFERENCES enrollments, absent_rate REAL NOT NULL);
"""

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

def query(sql, args=(), one=False):
    rows = get_db().execute(sql, args).fetchall()
    return (rows[0] if rows else None) if one else rows

def execute(sql, args=()):
    db = get_db(); cur = db.execute(sql, args); db.commit(); return cur.lastrowid

def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        get_db().executescript(SCHEMA)

def close_db(e=None):
    db = g.pop("db", None)
    if db is not None: db.close()
