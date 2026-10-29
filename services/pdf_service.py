from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak
)
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import (
    getSampleStyleSheet,
    ParagraphStyle
)
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.units import inch
from xml.sax.saxutils import escape
import re


# -------------------------
# CLEAN MARKDOWN (Wave 2)
# -------------------------

_TABLE_SEP = re.compile(r"^\s*\|?[\s:-]+\|[\s|:-]*$")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")


def clean_ai_text(text):
    """Strip markdown that breaks ReportLab Paragraph XML parsing."""
    if not text:
        return ""

    text = text.replace("₹", "Rs. ")
    # Fenced code blocks → plain text without fences
    text = re.sub(r"```[\w]*\n?", "", text)
    text = text.replace("```", "")

    kept = []
    for line in text.split("\n"):
        # Drop markdown pipe tables (ReportLab chokes on raw |)
        if _TABLE_ROW.match(line) or _TABLE_SEP.match(line):
            continue
        kept.append(line)
    text = "\n".join(kept)

    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"__(.*?)__", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"##\s*", "", text)
    text = re.sub(r"#\s*", "", text)
    # Collapse leftover HTML-ish tags to plain text
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?[^>]+>", "", text)

    return text


def _safe_xml(text: str) -> str:
    """Escape for ReportLab's mini-HTML Paragraph parser."""
    return escape(text or "", {"\"": "&quot;"})


# -------------------------
# PAGE FOOTER
# -------------------------

def add_page_number(canvas, doc):
    page_num = canvas.getPageNumber()

    canvas.setFont("Helvetica",9)

    canvas.drawRightString(
        550,
        25,
        f"Page {page_num}"
    )


# -------------------------
# PDF REPORT
# -------------------------

def generate_pdf_report(
    profile,
    health_data,
    ai_report,
    filename="financial_report.pdf"
):

    try:

        doc = SimpleDocTemplate(
            filename,
            pagesize=A4,
            leftMargin=55,
            rightMargin=55,
            topMargin=50,
            bottomMargin=50
        )

        styles = getSampleStyleSheet()

        cover_title = ParagraphStyle(
            "cover",
            fontName="Helvetica-Bold",
            fontSize=26,
            leading=34,
            alignment=TA_CENTER
        )

        subtitle = ParagraphStyle(
            "subtitle",
            fontSize=12,
            alignment=TA_CENTER,
            leading=20
        )

        heading = ParagraphStyle(
            "heading",
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=24,
            spaceAfter=12
        )

        body = ParagraphStyle(
            "body",
            fontSize=11,
            leading=19,
            alignment=TA_JUSTIFY
        )

        bullet = ParagraphStyle(
            "bullet",
            fontSize=11,
            leftIndent=18,
            leading=18
        )

        story=[]

        # =================================================
        # COVER PAGE
        # =================================================

        story.append(Spacer(1,2*inch))

        story.append(
            Paragraph(
                "PERSONAL FINANCIAL ADVISORY REPORT",
                cover_title
            )
        )

        story.append(Spacer(1,.4*inch))

        story.append(
            Paragraph(
                "Prepared by Monetra",
                subtitle
            )
        )

        story.append(
            Paragraph(
                "Confidential Client Advisory Document",
                subtitle
            )
        )

        story.append(Spacer(1,1.2*inch))

        cover_table=Table(
            [
                ["Client Age", profile["age"]],
                ["Risk Profile", str(profile["risk_appetite"])],
                ["Primary Goal", str(profile["financial_goals"])[:120]],
                ["Financial Health Score", f"{health_data['score']}/100"]
            ],
            colWidths=[220,180]
        )

        cover_table.setStyle(
            TableStyle([
                ("BOX",(0,0),(-1,-1),1,colors.grey),
                ("INNERGRID",(0,0),(-1,-1),0.5,colors.grey),
                ("BACKGROUND",(0,0),(0,-1),colors.whitesmoke),
                ("FONTNAME",(0,0),(-1,-1),"Helvetica"),
                ("PADDING",(0,0),(-1,-1),10)
            ])
        )

        story.append(cover_table)

        story.append(Spacer(1,2*inch))

        story.append(
            Paragraph(
                "Generated for educational financial planning purposes.",
                subtitle
            )
        )

        story.append(PageBreak())

        # =================================================
        # EXECUTIVE SUMMARY
        # =================================================

        story.append(
            Paragraph(
                "Executive Summary",
                heading
            )
        )

        summary=f"""
This advisory report evaluates the client's present financial condition,
risk profile, and alignment with long-term financial objectives.

Current assessment indicates a financial health score of
{health_data['score']}/100 and highlights optimization opportunities
across budgeting, savings discipline and investment planning.
"""

        story.append(
            Paragraph(summary,body)
        )

        story.append(Spacer(1,25))

        # ==========================================
        # FINANCIAL SNAPSHOT
        # ==========================================

        story.append(
            Paragraph(
                "Financial Snapshot",
                heading
            )
        )

        snapshot=Table(
            [
                ["Monthly Income",f"Rs. {profile['income']}"],
                ["Monthly Expenses",f"Rs. {profile['expenses']}"],
                ["Current Savings",f"Rs. {profile['savings']}"],
            ],
            colWidths=[220,180]
        )

        snapshot.setStyle(
            TableStyle([
                ("BOX",(0,0),(-1,-1),1,colors.grey),
                ("INNERGRID",(0,0),(-1,-1),0.5,colors.grey),
                ("BACKGROUND",(0,0),(0,-1),colors.whitesmoke),
                ("PADDING",(0,0),(-1,-1),10)
            ])
        )

        story.append(snapshot)

        story.append(Spacer(1,25))

        # ==========================================
        # INSIGHTS
        # ==========================================

        story.append(
            Paragraph(
                "Key Financial Insights",
                heading
            )
        )

        for item in health_data.get("insights") or []:
            item = _safe_xml(str(item).replace("₹", "Rs."))
            story.append(Paragraph(f"• {item}", bullet))

        story.append(Spacer(1,20))

        # ==========================================
        # WARNINGS
        # ==========================================

        story.append(
            Paragraph(
                "Risk Considerations",
                heading
            )
        )

        for item in health_data.get("warnings") or []:
            item = _safe_xml(str(item).replace("₹", "Rs."))
            story.append(Paragraph(f"• {item}", bullet))

        story.append(PageBreak())

        # ==========================================
        # AI RECOMMENDATIONS
        # ==========================================

        story.append(
            Paragraph(
                "Advisory Recommendations",
                heading
            )
        )

        cleaned = clean_ai_text(ai_report)

        for line in cleaned.split("\n"):
            line = line.strip()
            if not line:
                continue

            if any(
                line.startswith(x)
                for x in [
                    "Financial Summary",
                    "Budget Optimization",
                    "Investment Recommendations",
                    "Risk Warnings",
                    "Goal Strategy",
                    "30-Day Action Plan",
                ]
            ):
                story.append(Spacer(1, 10))
                story.append(Paragraph(_safe_xml(line), heading))
            elif line.startswith("-") or line.startswith("•"):
                content = line[1:].strip()
                story.append(Paragraph(f"• {_safe_xml(content)}", bullet))
            else:
                story.append(Paragraph(_safe_xml(line), body))

        story.append(Spacer(1,30))

        # ==========================================
        # ACTION CHECKLIST
        # ==========================================

        story.append(
            Paragraph(
                "Immediate Action Checklist",
                heading
            )
        )

        checklist=[
            "Review budget allocations",
            "Strengthen emergency reserves",
            "Begin disciplined investments",
            "Track progress quarterly",
            "Review risk exposure periodically"
        ]

        for item in checklist:
            story.append(
                Paragraph(
                    f"1. {item}",
                    bullet
                )
            )

        story.append(Spacer(1,30))

        # ==========================================
        # DISCLAIMER
        # ==========================================

        story.append(
            Paragraph(
                "Disclaimer",
                heading
            )
        )

        disclaimer="""
This report is AI-assisted educational financial guidance
and should not be treated as regulated investment advice.
Independent professional consultation is recommended before
investment decisions.
"""

        story.append(
            Paragraph(
                disclaimer,
                body
            )
        )

        doc.build(
            story,
            onFirstPage=add_page_number,
            onLaterPages=add_page_number
        )

        return True, filename

    except Exception as e:
        return False, str(e)