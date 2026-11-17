from flask import Blueprint, render_template, request, redirect, url_for, flash, g, abort, Response
from controllers import role_required
from database import AppError, query
from models.academic import Faculty, Course, ClassSection, Session
from models.attendance import AttendanceRule
from models.report import Report
from models.user import User

bp = Blueprint("admin", __name__, url_prefix="/admin")
admin_only = role_required("ADMIN")
F = lambda k: request.form.get(k, "")

@bp.route("/")
@admin_only
def users():
    q, role = request.args.get("q", "").strip(), request.args.get("role", "")
    sql = """SELECT u.*, COALESCE(s.student_code, l.lecturer_code, '') AS code FROM users u
        LEFT JOIN students s USING(user_id) LEFT JOIN lecturers l USING(user_id) WHERE 1=1"""
    args = []
    if q: sql += " AND (u.username LIKE ? OR u.full_name LIKE ? OR u.email LIKE ?)"; args += [f"%{q}%"] * 3
    if role in ("STUDENT", "LECTURER"): sql += " AND u.role=?"; args.append(role)
    return render_template("admin_users.html", users=query(sql + " ORDER BY u.role, u.username", args), q=q, role=role)

@bp.route("/users/new", methods=["GET", "POST"])
@admin_only
def new_user():
    if request.method == "POST":
        try:
            g.user.manage_accounts(F("role"), F("username"), F("password"), F("full_name"), F("email"), F("phone"), F("code"), F("major"), F("dob"))
            flash("Account created.", "ok"); return redirect(url_for("admin.users"))
        except AppError as e: flash(str(e), "error")
    return render_template("user_form.html", u=None)

@bp.route("/users/<int:uid>/edit", methods=["GET", "POST"])
@admin_only
def edit_user(uid):
    u = query("SELECT * FROM users WHERE user_id=?", (uid,), one=True)
    if not u: abort(404)
    if request.method == "POST":
        try:
            g.user.update_account(uid, F("full_name"), F("email"), F("phone")); flash("Account updated.", "ok")
            return redirect(url_for("admin.users"))
        except AppError as e: flash(str(e), "error")
    return render_template("user_form.html", u=u)

@bp.route("/users/<int:uid>/<action>", methods=["GET", "POST"])
@admin_only
def lock(uid, action):
    if action not in ("lock", "unlock"): abort(404)
    u = User.get(uid)
    if not u: abort(404)
    if request.method == "POST":
        try: g.user.set_locked(uid, action == "lock"); flash(f"Account {action}ed.", "ok")
        except AppError as e: flash(str(e), "error")
        return redirect(url_for("admin.users"))
    return render_template("confirm.html", u=u, action=action)

@bp.route("/users/import", methods=["POST"])
@admin_only
def import_students():
    try:
        n, errs = g.user.import_students(request.files.get("file")); flash(f"Imported {n} student(s).", "ok")
        for e in errs[:10]: flash(e, "error")
    except AppError as e: flash(str(e), "error")
    return redirect(url_for("admin.users"))

@bp.route("/courses", methods=["GET", "POST"])
@admin_only
def courses():
    if request.method == "POST":
        try:
            kind = F("kind")
            if kind == "faculty": Faculty.create(F("name"))
            elif kind == "course": g.user.manage_courses(F("code"), F("name"), F("credits"), F("total_sessions"), request.form.get("faculty_id", type=int))
            elif kind == "class": g.user.manage_classes(F("code"), F("name"), F("semester"), request.form.get("course_id", type=int), request.form.get("lecturer_id", type=int))
            else: abort(400)
            flash("Saved.", "ok")
        except AppError as e: flash(str(e), "error")
        return redirect(url_for("admin.courses"))
    return render_template("admin_courses.html", faculties=Faculty.all(), courses=Course.all(), classes=ClassSection.all(),
                           lecturers=query("SELECT u.user_id, u.full_name, l.lecturer_code FROM lecturers l JOIN users u ON u.user_id=l.user_id ORDER BY u.full_name"))

@bp.route("/classes/<int:cid>", methods=["GET", "POST"])
@admin_only
def class_page(cid):
    c = ClassSection.get(cid)
    if not c: abort(404)
    if request.method == "POST":
        try:
            kind = F("kind")
            if kind == "session": Session.create(cid, F("date"), F("start"), F("end"), F("room"))
            elif kind == "enroll": ClassSection.add_student(cid, F("student_code"))
            elif kind == "remove": ClassSection.remove_student(cid, request.form.get("student_id", type=int))
            else: abort(400)
            flash("Saved.", "ok")
        except AppError as e: flash(str(e), "error")
        return redirect(url_for("admin.class_page", cid=cid))
    return render_template("admin_class.html", c=c, sessions=Session.for_class(cid), students=ClassSection.students(cid))

@bp.route("/rules", methods=["GET", "POST"])
@admin_only
def rules():
    if request.method == "POST":
        try: g.user.configure_rules(F("qr"), F("late"), F("max")); flash("Rules saved.", "ok"); return redirect(url_for("admin.rules"))
        except AppError as e: flash(str(e), "error")
    return render_template("rules.html", r=AttendanceRule.get())

def _flt():
    return {"faculty_id": request.args.get("faculty_id", type=int), "course_id": request.args.get("course_id", type=int),
            "class_id": request.args.get("class_id", type=int), "keyword": request.args.get("q", "")}

@bp.route("/stats")
@admin_only
def stats():
    f = _flt()
    return render_template("report.html", rows=g.user.view_statistics(**f), classes=ClassSection.all(), faculties=Faculty.all(),
                           courses=Course.all(), f=f, export_ep="admin.export", title="University Statistics")

@bp.route("/stats/export/<fmt>")
@admin_only
def export(fmt):
    if fmt not in ("xlsx", "pdf"): abort(404)
    rows = g.user.view_statistics(**_flt()); Report.log(g.user.user_id, "statistics", fmt)
    data = Report.export_excel(rows) if fmt == "xlsx" else Report.export_pdf(rows)
    mime = "application/pdf" if fmt == "pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return Response(data, mimetype=mime, headers={"Content-Disposition": f"attachment; filename=statistics.{fmt}"})
