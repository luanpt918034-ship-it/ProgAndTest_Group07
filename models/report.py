"""Report: filter / search attendance statistics and export to Excel or PDF."""
import io
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from database import query, execute, now

HEADERS = ["Class", "Course", "Student code", "Student name", "Present", "Late", "Absent", "Excused", "Absence rate (%)"]

class Report:
    @staticmethod
    def filter(lecturer_id=None, faculty_id=None, course_id=None, class_id=None, keyword=""):
        sql = """SELECT cs.class_code, c.course_name, s.student_code, u.full_name,
            SUM(r.status='PRESENT') AS present, SUM(r.status='LATE') AS late, SUM(r.status='ABSENT') AS absent,
            SUM(r.status='EXCUSED') AS excused, c.total_sessions
            FROM enrollments e JOIN class_sections cs USING(class_id) JOIN courses c USING(course_id)
            JOIN students s ON s.user_id=e.student_id JOIN users u ON u.user_id=s.user_id
            LEFT JOIN class_sessions x ON x.class_id=cs.class_id
            LEFT JOIN attendance_sessions a ON a.class_session_id=x.class_session_id
            LEFT JOIN attendance_records r ON r.att_session_id=a.att_session_id AND r.student_id=s.user_id
            WHERE 1=1"""
        args = []
        for col, v in (("cs.lecturer_id", lecturer_id), ("c.faculty_id", faculty_id), ("c.course_id", course_id), ("cs.class_id", class_id)):
            if v not in (None, ""): sql += f" AND {col}=?"; args.append(v)
        if keyword and keyword.strip():
            sql += " AND (u.full_name LIKE ? OR s.student_code LIKE ?)"; args += [f"%{keyword.strip()}%"] * 2
        sql += " GROUP BY e.enrollment_id ORDER BY cs.class_code, s.student_code"
        out = []
        for r in query(sql, args):
            d = dict(r)
            for k in ("present", "late", "absent", "excused"): d[k] = d[k] or 0
            d["rate"] = round(100.0 * d["absent"] / d["total_sessions"], 2)
            out.append(d)
        return out

    search = filter     # class diagram: filter(criteria) / search(keyword)

    @staticmethod
    def _rows(rows):
        return [[r["class_code"], r["course_name"], r["student_code"], r["full_name"], r["present"], r["late"],
                 r["absent"], r["excused"], r["rate"]] for r in rows]

    @staticmethod
    def export_excel(rows):
        wb = Workbook(); ws = wb.active; ws.title = "Attendance"; ws.append(HEADERS)
        for r in Report._rows(rows): ws.append(r)
        buf = io.BytesIO(); wb.save(buf); return buf.getvalue()

    @staticmethod
    def export_pdf(rows):
        buf = io.BytesIO(); doc = SimpleDocTemplate(buf, pagesize=landscape(A4))
        t = Table([HEADERS] + Report._rows(rows), repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.lightblue), ("GRID", (0, 0), (-1, -1), .4, colors.grey),
                               ("FONTSIZE", (0, 0), (-1, -1), 8)]))
        doc.build([Paragraph("Attendance Report", getSampleStyleSheet()["Title"]), t]); return buf.getvalue()

    @staticmethod
    def log(user_id, rtype, fmt):
        execute("INSERT INTO reports(generated_by,report_type,file_format,generated_at) VALUES(?,?,?,?)", (user_id, rtype, fmt, now()))
