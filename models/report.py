"""Report: filter / search attendance statistics and export to Excel or PDF."""
import io
import os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from database import query, execute, now

HEADERS = ["Class", "Course", "Student code", "Student name", "Present", "Late", "Absent", "Excused", "Absence rate (%)"]


def _register_vietnamese_fonts():
    """Register Unicode TrueType fonts supporting Vietnamese diacritics for ReportLab."""
    regular_candidates = [
        os.path.join(os.path.dirname(__file__), "..", "static", "fonts", "LiberationSans-Regular.ttf"),
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    bold_candidates = [
        os.path.join(os.path.dirname(__file__), "..", "static", "fonts", "LiberationSans-Bold.ttf"),
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    reg_path = next((p for p in regular_candidates if os.path.exists(p)), None)
    bold_path = next((p for p in bold_candidates if os.path.exists(p)), None)

    if reg_path:
        if "ReportVN" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("ReportVN", reg_path))
        if bold_path and "ReportVN-Bold" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("ReportVN-Bold", bold_path))
            return "ReportVN", "ReportVN-Bold"
        return "ReportVN", "ReportVN"
    return "Helvetica", "Helvetica-Bold"


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
            if v not in (None, ""):
                sql += f" AND {col}=?"
                args.append(v)
        if keyword and keyword.strip():
            sql += " AND (u.full_name LIKE ? OR s.student_code LIKE ?)"
            args += [f"%{keyword.strip()}%"] * 2
        sql += " GROUP BY e.enrollment_id ORDER BY cs.class_code, s.student_code"
        out = []
        for r in query(sql, args):
            d = dict(r)
            for k in ("present", "late", "absent", "excused"):
                d[k] = d[k] or 0
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
        wb = Workbook()
        ws = wb.active
        ws.title = "Attendance"

        # Row 1 MUST remain the table header row so unit tests (max_row = len(rows) + 1) pass
        ws.append(HEADERS)

        header_fill = PatternFill(start_color="002B64", end_color="002B64", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        zebra_fill = PatternFill(start_color="FBFCFE", end_color="FBFCFE", fill_type="solid")
        white_fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
        warn_fill = PatternFill(start_color="FCEEEF", end_color="FCEEEF", fill_type="solid")
        warn_font = Font(name="Calibri", size=10, bold=True, color="C43F48")
        body_font = Font(name="Calibri", size=10, color="142338")
        thin_side = Side(border_style="thin", color="DCE4EE")
        cell_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

        ws.row_dimensions[1].height = 26
        for col_idx in range(1, len(HEADERS) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.border = cell_border
            cell.alignment = Alignment(
                horizontal="center" if col_idx >= 5 or col_idx in (1, 3) else "left",
                vertical="center",
            )

        data_rows = Report._rows(rows)
        for row_offset, r in enumerate(data_rows, start=2):
            ws.append(r)
            ws.row_dimensions[row_offset].height = 22
            row_fill = zebra_fill if row_offset % 2 == 1 else white_fill
            for col_idx in range(1, len(HEADERS) + 1):
                cell = ws.cell(row=row_offset, column=col_idx)
                cell.border = cell_border
                cell.font = body_font
                cell.fill = row_fill
                if col_idx in (1, 3, 5, 6, 7, 8):
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                elif col_idx == 9:
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                    cell.number_format = "0.00"
                    if isinstance(cell.value, (int, float)) and cell.value > 20:
                        cell.fill = warn_fill
                        cell.font = warn_font
                else:
                    cell.alignment = Alignment(horizontal="left", vertical="center")

        min_widths = [14, 28, 16, 26, 11, 10, 11, 11, 18]
        for col_idx, min_w in enumerate(min_widths, start=1):
            col_letter = get_column_letter(col_idx)
            max_len = min_w
            for row_idx in range(1, len(data_rows) + 2):
                val = ws.cell(row=row_idx, column=col_idx).value
                if val is not None:
                    max_len = max(max_len, len(str(val)) + 4)
            ws.column_dimensions[col_letter].width = min(max_len, 42)

        ws.freeze_panes = "A2"
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    @staticmethod
    def export_pdf(rows):
        font_reg, font_bold = _register_vietnamese_fonts()
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=landscape(A4),
            leftMargin=28,
            rightMargin=28,
            topMargin=28,
            bottomMargin=28,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "ReportTitleVN",
            parent=styles["Title"],
            fontName=font_bold,
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#002B64"),
            spaceAfter=4,
            alignment=0,
        )
        meta_style = ParagraphStyle(
            "ReportMetaVN",
            parent=styles["Normal"],
            fontName=font_reg,
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#66758A"),
            spaceAfter=12,
        )
        cell_style = ParagraphStyle(
            "TableCellVN",
            parent=styles["Normal"],
            fontName=font_reg,
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#142338"),
        )
        header_cell_style = ParagraphStyle(
            "TableHeaderVN",
            parent=styles["Normal"],
            fontName=font_bold,
            fontSize=8.5,
            leading=11,
            textColor=colors.white,
        )

        table_data = [[Paragraph(h, header_cell_style) for h in HEADERS]]
        for r in Report._rows(rows):
            table_data.append([
                Paragraph(str(r[0]), cell_style),
                Paragraph(str(r[1]), cell_style),
                Paragraph(str(r[2]), cell_style),
                Paragraph(str(r[3]), cell_style),
                str(r[4]),
                str(r[5]),
                str(r[6]),
                str(r[7]),
                f"{float(r[8]):.2f}%",
            ])

        if len(table_data) == 1:
            table_data.append([Paragraph("No attendance records found.", cell_style)] + [""] * 8)

        col_widths = [68, 155, 82, 155, 55, 50, 55, 58, 88]
        t = Table(table_data, colWidths=col_widths, repeatRows=1)

        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002B64")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), font_bold),
            ("FONTNAME", (0, 1), (-1, -1), font_reg),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("ALIGN", (0, 1), (0, -1), "CENTER"),
            ("ALIGN", (2, 1), (2, -1), "CENTER"),
            ("ALIGN", (4, 1), (7, -1), "CENTER"),
            ("ALIGN", (8, 1), (8, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DCE4EE")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FBFCFE")]),
        ]

        for idx, r in enumerate(rows, start=1):
            if r.get("rate", 0) > 20:
                style_cmds.append(("BACKGROUND", (8, idx), (8, idx), colors.HexColor("#FCEEEF")))
                style_cmds.append(("TEXTCOLOR", (8, idx), (8, idx), colors.HexColor("#C43F48")))
                style_cmds.append(("FONTNAME", (8, idx), (8, idx), font_bold))

        t.setStyle(TableStyle(style_cmds))

        story = [
            Paragraph("Attendance Report", title_style),
            Paragraph(f"Generated at: {now()} &nbsp;&bull;&nbsp; Total records: {len(rows)}", meta_style),
            t,
        ]
        doc.build(story)
        return buf.getvalue()

    @staticmethod
    def log(user_id, rtype, fmt):
        execute("INSERT INTO reports(generated_by,report_type,file_format,generated_at) VALUES(?,?,?,?)", (user_id, rtype, fmt, now()))
