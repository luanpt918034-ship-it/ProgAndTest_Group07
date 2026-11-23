from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from controllers import role_required, rate_limited
from database import AppError, query
from models.academic import ClassSection, Session
from models.attendance import Notification, AbsenceRequest

bp = Blueprint("student", __name__, url_prefix="/student")
student_only = role_required("STUDENT")

@bp.route("/")
@student_only
def dashboard():
    return render_template("student_dashboard.html", today=Session.today_for_student(g.user.user_id),
                           notes=Notification.for_user(g.user.user_id, unread_only=True))

@bp.route("/notifications/read", methods=["POST"])
@student_only
def read_notes():
    Notification.mark_all_read(g.user.user_id); return redirect(url_for("student.dashboard"))

@bp.route("/courses")
@student_only
def courses(): return render_template("student_courses.html", classes=ClassSection.for_student(g.user.user_id))

@bp.route("/scan", methods=["GET", "POST"])
@student_only
def scan():
    if request.method == "POST":
        if rate_limited(("scan", g.user.user_id), limit=10): flash("Too many attempts. Please wait a minute.", "error")
        else:
            try:
                st = g.user.scan_qr(request.form.get("token", ""))
                flash(f"Check-in successful. Your status: {st.title()}.", "ok")
            except AppError as e: flash(str(e), "error")
        return redirect(url_for("student.scan"))
    return render_template("scan.html")

@bp.route("/history")
@student_only
def history():
    cid = request.args.get("class_id", type=int)
    return render_template("history.html", data=g.user.view_history(cid), classes=ClassSection.for_student(g.user.user_id), cid=cid)

@bp.route("/absence", methods=["GET", "POST"])
@student_only
def absence():
    if request.method == "POST":
        try:
            g.user.submit_absence_request(request.form.get("class_session_id", type=int), request.form.get("reason", ""),
                                          request.files.get("attachment"))
            flash("Absence request submitted.", "ok"); return redirect(url_for("student.absence"))
        except AppError as e: flash(str(e), "error")
    sessions = query("""SELECT cs.class_session_id, cs.session_date, c.class_name FROM class_sessions cs
        JOIN class_sections c USING(class_id) JOIN enrollments e ON e.class_id=c.class_id
        WHERE e.student_id=? ORDER BY cs.session_date DESC""", (g.user.user_id,))
    return render_template("absence.html", sessions=sessions, requests=AbsenceRequest.for_student(g.user.user_id))
