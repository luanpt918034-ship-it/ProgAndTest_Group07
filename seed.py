"""Demo data. Run: python seed.py   (accounts: admin/admin123, lecturer01/123456, student01..05/123456)"""
from datetime import date, timedelta
from werkzeug.security import generate_password_hash
from app import create_app
from database import query, execute, now
from models.user import Admin
from models.academic import Faculty, Course, ClassSection, Session
from models.attendance import AttendanceRule

def seed(app):
    with app.app_context():
        if query("SELECT 1 FROM users LIMIT 1", one=True): return False
        aid = execute("INSERT INTO users(username,password_hash,full_name,email,phone,role,created_at) VALUES(?,?,?,?,?,'ADMIN',?)",
                      ("admin", generate_password_hash("admin123"), "System Admin", "admin@uni.edu", "", now()))
        admin = Admin(query("SELECT * FROM users WHERE user_id=?", (aid,), one=True))
        AttendanceRule.update(aid, 10, 5, 20)
        lid = admin.manage_accounts("LECTURER", "lecturer01", "123456", "Dr. Nguyen Van A", "lecturer01@uni.edu", code="GV001")
        for i in range(1, 6):
            admin.manage_accounts("STUDENT", f"student0{i}", "123456", f"Student {i}", f"student0{i}@uni.edu", code=f"SV00{i}", major="Software Engineering")
        fid = Faculty.create("Information Technology")
        cid = Course.create("SE101", "Software Engineering", 3, 10, fid)
        cls = ClassSection.create("SE101.01", "Software Engineering - Group 1", "2026-1", cid, lid)
        for i in range(1, 6): ClassSection.add_student(cls, f"SV00{i}")
        today = date.today()
        for d in (-7, 0, 7): Session.create(cls, (today + timedelta(days=d)).isoformat(), "07:00", "09:30", "A101")
        return True

if __name__ == "__main__":
    print("Seeded." if seed(create_app()) else "Database already has data.")
