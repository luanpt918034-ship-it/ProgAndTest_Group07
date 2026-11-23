from flask import Blueprint, render_template, request, redirect, url_for, flash, g, abort, Response
from controllers import role_required
from database import AppError, query
from models.academic import ClassSection, Session
from models.attendance import AttendanceSession, AttendanceRecord, AbsenceRequest, STATUSES
from models.report import Report

bp = Blueprint("lecturer", __name__, url_prefix="/lecturer")
lecturer_only = role_required("LECTURER")

def _own_class(class_id):
    if not g.user.owns_class(class_id): abort(403)
    return ClassSection.get(class_id)

@bp.route("/")
@lecturer_only
def dashboard():
    return render_template("lecturer_dashboard.html", classes=ClassSection.for_lecturer(g.user.user_id),
                           today=Session.today_for_lecturer(g.user.user_id),
                           pending=len(AbsenceRequest.for_lecturer(g.user.user_id, "PENDING")))

@bp.route("/class/<int:class_id>")
@lecturer_only
def class_details(class_id):
    return render_template("class_details.html", c=_own_class(class_id), sessions=Session.for_class(class_id),
                           students=ClassSection.students(class_id))

@bp.route("/session/<int:csid>/open", methods=["POST"])
@lecturer_only
def open_session(csid):
    try: return redirect(url_for("lecturer.qr", att_id=g.user.open_session(csid)))
    except AppError as e:
        flash(str(e), "error"); return redirect(request.referrer or url_for("lecturer.dashboard"))

def _own_att(att_id):
    a = AttendanceSession.get(att_id)
    if not a: abort(404)
    cs = query("SELECT cs.*, c.lecturer_id, c.class_name FROM class_sessions cs JOIN class_sections c USING(class_id) WHERE class_session_id=?",
               (a["class_session_id"],), one=True)
    if cs["lecturer_id"] != g.user.user_id: abort(403)
    return a, cs

@bp.route("/attendance/<int:att_id>")
@lecturer_only
def qr(att_id):
    a, cs = _own_att(att_id)
    return render_template("qr.html", a=a, cs=cs, rows=AttendanceRecord.for_session(a["class_session_id"]))

@bp.route("/attendance/<int:att_id>/close", methods=["POST"])
@lecturer_only
def close_session(att_id):
    a, cs = _own_att(att_id)
    try: n = g.user.close_session(att_id); flash(f"Attendance closed. {n} student(s) marked absent.", "ok")
    except AppError as e: flash(str(e), "error")
    return redirect(url_for("lecturer.class_details", class_id=cs["class_id"]))

@bp.route("/manual/<int:csid>", methods=["GET", "POST"])
@lecturer_only
def manual(csid):
    cs = query("SELECT cs.*, c.lecturer_id, c.class_name FROM class_sessions cs JOIN class_sections c USING(class_id) WHERE class_session_id=?", (csid,), one=True)
    if not cs: abort(404)
    if cs["lecturer_id"] != g.user.user_id: abort(403)
    if request.method == "POST":
        done = 0
        for r in AttendanceRecord.for_session(csid):
            new = request.form.get(f"status_{r['user_id']}", "")
            if not new or new == r["status"]: continue
            try: g.user.mark_manually(csid, r["user_id"], new, request.form.get(f"reason_{r['user_id']}", "")); done += 1
            except AppError as e: flash(f"{r['student_code']}: {e}", "error")
        if done: flash(f"{done} record(s) updated.", "ok")
        return redirect(url_for("lecturer.manual", csid=csid))
    return render_template("manual.html", cs=cs, rows=AttendanceRecord.for_session(csid), logs=AttendanceRecord.logs(csid), statuses=STATUSES)

@bp.route("/absences")
@lecturer_only
def absences(): return render_template("absences.html", reqs=AbsenceRequest.for_lecturer(g.user.user_id))

@bp.route("/absences/<int:rid>/<action>", methods=["POST"])
@lecturer_only
def review(rid, action):
    if action not in ("approve", "reject"): abort(404)
    try: flash(f"Request {g.user.review_request(rid, action == 'approve').lower()}.", "ok")
    except AppError as e: flash(str(e), "error")
    return redirect(url_for("lecturer.absences"))

@bp.route("/report")
@lecturer_only
def report():
    flt = {"class_id": request.args.get("class_id", type=int), "keyword": request.args.get("q", "")}
    return render_template("report.html", rows=Report.filter(lecturer_id=g.user.user_id, **flt), classes=ClassSection.for_lecturer(g.user.user_id),
                           f=flt, export_ep="lecturer.export", title="Class Attendance Report")

@bp.route("/report/export/<fmt>")
@lecturer_only
def export(fmt):
    if fmt not in ("xlsx", "pdf"): abort(404)
    data = g.user.export_report(fmt, class_id=request.args.get("class_id", type=int), keyword=request.args.get("q", ""))
    mime = "application/pdf" if fmt == "pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return Response(data, mimetype=mime, headers={"Content-Disposition": f"attachment; filename=attendance.{fmt}"})
