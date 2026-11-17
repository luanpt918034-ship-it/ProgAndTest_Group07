# Student Attendance System (QR) – Group 07

Web app (Python / Flask / SQLite) with a browser GUI, responsive for desktop and mobile.

## Run
```
pip install -r requirements.txt
python seed.py          # demo data
python app.py           # http://localhost:5000
```
Docker: `docker compose up --build`.  Tests: `python -m unittest discover -v` (70 automated test cases).

Demo accounts: `admin/admin123`, `lecturer01/123456`, `student01..student05/123456`.
In development, reset-password emails are written to the log; set `SMTP_HOST` (and `SMTP_PORT`, `SMTP_FROM`) to send real mail.

## Architecture: MVC (Chapter 3)
| Layer | Folder | Content |
|---|---|---|
| Model | `models/`, `database.py` | OOP classes of the class diagram: abstract `User` → `Admin`/`Lecturer`/`Student`; `Faculty`, `Course`, `ClassSection`, `Session`; `AttendanceRule`, `AttendanceSession`, `AttendanceRecord`, `AbsenceRequest`, `AttendanceAlert`, `Notification`, `Report`. Tables follow the ERD. |
| View | `templates/`, `static/` | One page per screen in section VII of the spec. |
| Controller | `controllers/` | Routes per role (`auth`, `student`, `lecturer`, `admin`), role checks, CSRF, rate limiting. |

## Use case → route
UC1-3 `/login`, `/forgot`, `/reset/<token>`, `/password`, `/profile` · UC4 `/admin/courses`, `/admin/classes/<id>` · UC5 `/admin/` (+ import) ·
UC6 `/admin/rules` · UC7 `/lecturer/session/<id>/open`, `/lecturer/attendance/<id>` · UC8 `/student/scan` · UC9 `/lecturer/manual/<id>` ·
UC10 `/student/absence`, `/lecturer/absences` · UC11 `/student/history` · UC12 `/lecturer/report`, `/admin/stats` (Excel/PDF export) · UC13 `/student/courses`.

## Notes / assumptions
- Late threshold is counted from the moment the Lecturer opens the attendance session.
- When a session is closed, enrolled students without a check-in become *Absent*; absence rate = Absent / total sessions of the course.
- Imported students get the initial password `<student_code>@123`.
- QR image and camera scanning use CDN libraries (qrcodejs, html5-qrcode); the 64-char code can also be typed manually.
- Security: salted password hashes, hashed single-use reset tokens, parameterised SQL, Jinja auto-escaping, CSRF tokens, login/scan rate limit.
