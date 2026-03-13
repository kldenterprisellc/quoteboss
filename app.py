import os
import io
import json
import uuid
import base64
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, send_file, abort
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

app = Flask(__name__)

# In-memory quote store (stateless MVP — quotes expire on restart)
quote_store = {}

# ─────────────────────────────────────────────
# Pricing data
# ─────────────────────────────────────────────
PRICING = {
    "HVAC": {
        "AC Install":       {"min": 3500, "max": 7500, "unit": "job"},
        "AC Repair":        {"min": 150,  "max": 600,  "unit": "job"},
        "Furnace Install":  {"min": 2500, "max": 6000, "unit": "job"},
        "Furnace Repair":   {"min": 130,  "max": 500,  "unit": "job"},
        "Duct Cleaning":    {"min": 300,  "max": 700,  "unit": "job"},
        "Mini Split":       {"min": 2000, "max": 5500, "unit": "job"},
    },
    "Plumbing": {
        "Water Heater":     {"min": 800,  "max": 2000, "unit": "job"},
        "Pipe Repair":      {"min": 150,  "max": 500,  "unit": "job"},
        "Drain Cleaning":   {"min": 100,  "max": 350,  "unit": "job"},
        "Bathroom Remodel": {"min": 1500, "max": 4000, "unit": "job"},
        "Sewer Line":       {"min": 1000, "max": 4500, "unit": "job"},
        "Faucet Install":   {"min": 100,  "max": 350,  "unit": "job"},
    },
    "Electrical": {
        "Panel Upgrade":    {"min": 1500, "max": 4000, "unit": "job"},
        "Outlet Install":   {"min": 100,  "max": 250,  "unit": "job"},
        "Lighting":         {"min": 150,  "max": 500,  "unit": "job"},
        "Ceiling Fan":      {"min": 100,  "max": 300,  "unit": "job"},
        "EV Charger":       {"min": 500,  "max": 1500, "unit": "job"},
        "Rewire":           {"min": 8000, "max": 20000,"unit": "job"},
    },
    "Roofing": {
        "Full Replacement": {"min": 350,  "max": 700,  "unit": "per sq (100 sqft)"},
        "Repair":           {"min": 150,  "max": 500,  "unit": "job"},
        "Gutters":          {"min": 600,  "max": 2400, "unit": "job"},
        "Skylight":         {"min": 900,  "max": 2300, "unit": "job"},
    },
    "Landscaping": {
        "Lawn Maintenance": {"min": 100,  "max": 300,  "unit": "per month"},
        "Sod":              {"min": 1,    "max": 3,    "unit": "per sqft"},
        "Tree Removal":     {"min": 300,  "max": 2000, "unit": "job"},
        "Sprinkler System": {"min": 1500, "max": 3500, "unit": "job"},
        "Full Design":      {"min": 3000, "max": 15000,"unit": "job"},
    },
    "General": {
        "Handyman Services":{"min": 75,   "max": 200,  "unit": "per hour"},
        "Painting (int.)":  {"min": 900,  "max": 2800, "unit": "job"},
        "Painting (ext.)":  {"min": 1500, "max": 4500, "unit": "job"},
        "Flooring":         {"min": 3,    "max": 12,   "unit": "per sqft"},
        "Drywall Repair":   {"min": 200,  "max": 700,  "unit": "job"},
        "Deck Build":       {"min": 4000, "max": 12000,"unit": "job"},
    },
}

# Regional cost multipliers (rough estimates)
REGION_MULTIPLIERS = {
    "CA": 1.35, "NY": 1.30, "MA": 1.25, "WA": 1.20, "CO": 1.15,
    "OR": 1.15, "IL": 1.10, "FL": 1.05, "TX": 1.00, "AZ": 1.00,
    "GA": 0.95, "NC": 0.95, "OH": 0.95, "MI": 0.95, "PA": 1.05,
    "NJ": 1.25, "CT": 1.20, "VA": 1.00, "TN": 0.90, "AL": 0.88,
    "MS": 0.88, "AR": 0.88, "KY": 0.90, "IN": 0.92, "MO": 0.92,
    "WI": 0.95, "MN": 1.00, "IA": 0.90, "KS": 0.90, "NE": 0.90,
    "OK": 0.90, "LA": 0.93, "SC": 0.92, "WV": 0.88, "MT": 0.92,
    "ID": 0.92, "NV": 1.05, "NM": 0.90, "UT": 0.98, "WY": 0.90,
    "ND": 0.90, "SD": 0.90, "HI": 1.40, "AK": 1.30,
}

LABOR_RATE = 85  # $ per hour base


def get_state_from_location(location: str) -> str:
    """Extract state abbreviation from 'City, ST' format."""
    parts = location.strip().upper().split(",")
    if len(parts) >= 2:
        return parts[-1].strip()[:2]
    # Try last two chars if no comma
    return location.strip().upper()[-2:]


def calculate_quote(data: dict) -> dict:
    trade = data["trade"]
    job_type = data["job_type"]
    property_size = float(data.get("property_size", 1500))
    location = data.get("location", "")
    labor_hours = float(data.get("labor_hours", 4))
    materials = data.get("materials", [])

    pricing = PRICING.get(trade, {}).get(job_type)
    if not pricing:
        raise ValueError(f"Unknown trade/job combination: {trade} / {job_type}")

    state = get_state_from_location(location)
    multiplier = REGION_MULTIPLIERS.get(state, 1.0)

    # Base price range from pricing table
    base_min = pricing["min"]
    base_max = pricing["max"]
    unit = pricing["unit"]

    # Scale by sqft for sqft-based jobs
    if "sqft" in unit:
        base_min = base_min * property_size
        base_max = base_max * property_size
    elif "per sq" in unit:
        # Roofing "squares" = 100 sqft
        squares = property_size / 100
        base_min = base_min * squares
        base_max = base_max * squares

    # Apply regional multiplier
    base_min = base_min * multiplier
    base_max = base_max * multiplier

    # Labor line
    labor_min = labor_hours * LABOR_RATE * 0.9
    labor_max = labor_hours * LABOR_RATE * 1.1

    # Materials line (rough estimate: 30% of base mid)
    materials_count = len(materials)
    mat_base = (base_min + base_max) / 2 * 0.30
    materials_min = mat_base * 0.85 if materials_count > 0 else 0
    materials_max = mat_base * 1.15 if materials_count > 0 else 0

    # For jobs where materials are separate (not bundled)
    if unit in ("job",) and materials_count > 0:
        total_min = base_min + labor_min + materials_min
        total_max = base_max + labor_max + materials_max
    else:
        total_min = base_min + labor_min
        total_max = base_max + labor_max

    # Round to nearest $50
    def r50(v):
        return round(v / 50) * 50

    line_items = [
        {
            "description": f"{job_type} — {trade} Service",
            "detail": f"Base estimate ({unit})",
            "min": r50(base_min),
            "max": r50(base_max),
        },
        {
            "description": "Labor",
            "detail": f"{labor_hours:.1f} hrs @ ${LABOR_RATE}/hr (regional adj.)",
            "min": r50(labor_min),
            "max": r50(labor_max),
        },
    ]

    if materials_count > 0:
        line_items.append({
            "description": "Materials & Supplies",
            "detail": ", ".join(materials),
            "min": r50(materials_min),
            "max": r50(materials_max),
        })

    return {
        "line_items": line_items,
        "total_min": r50(total_min),
        "total_max": r50(total_max),
        "multiplier": multiplier,
        "state": state,
        "unit": unit,
    }


# ─────────────────────────────────────────────
# PDF Generation
# ─────────────────────────────────────────────
NAVY = colors.HexColor("#0B1F3A")
ORANGE = colors.HexColor("#FF6B00")
LIGHT_GRAY = colors.HexColor("#F5F5F5")
MID_GRAY = colors.HexColor("#888888")
WHITE = colors.white


def generate_pdf(quote_data: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    story = []

    # ── Header ──────────────────────────────────────
    header_data = [[
        Paragraph(
            f"<font color='#FF6B00'><b>{quote_data['contractor_business'] or 'Your Business'}</b></font>",
            ParagraphStyle("biz", fontSize=18, textColor=NAVY, spaceAfter=2)
        ),
        Paragraph(
            "<font color='#FF6B00'><b>QUOTE</b></font>",
            ParagraphStyle("qlabel", fontSize=26, textColor=ORANGE, alignment=TA_RIGHT)
        ),
    ]]
    header_table = Table(header_data, colWidths=[4 * inch, 3 * inch])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("TOPPADDING", (0, 0), (-1, -1), 16),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
        ("LEFTPADDING", (0, 0), (0, -1), 20),
        ("RIGHTPADDING", (-1, 0), (-1, -1), 20),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.2 * inch))

    # ── Contractor + Client info ─────────────────────
    contractor_name = quote_data.get("contractor_name", "")
    contractor_phone = quote_data.get("contractor_phone", "")
    contractor_email = quote_data.get("contractor_email", "")
    client_name = quote_data.get("client_name", "")
    client_address = quote_data.get("client_address", "")
    location = quote_data.get("location", "")

    issue_date = datetime.now().strftime("%B %d, %Y")
    valid_until = (datetime.now() + timedelta(days=30)).strftime("%B %d, %Y")
    quote_number = quote_data.get("quote_id", str(uuid.uuid4())[:8].upper())

    meta_style = ParagraphStyle("meta", fontSize=9, leading=14, textColor=colors.HexColor("#333333"))
    label_style = ParagraphStyle("label", fontSize=8, textColor=MID_GRAY, leading=12)

    from_block = [
        Paragraph("<b>FROM</b>", label_style),
        Paragraph(f"<b>{contractor_name}</b>", ParagraphStyle("cn", fontSize=10, leading=14)),
        Paragraph(contractor_phone, meta_style),
        Paragraph(contractor_email, meta_style),
    ]

    to_block = [
        Paragraph("<b>PREPARED FOR</b>", label_style),
        Paragraph(f"<b>{client_name}</b>", ParagraphStyle("cl", fontSize=10, leading=14)),
        Paragraph(client_address, meta_style),
        Paragraph(location, meta_style),
    ]

    details_block = [
        Paragraph("<b>QUOTE DETAILS</b>", label_style),
        Paragraph(f"<b>Quote #:</b> {quote_number}", meta_style),
        Paragraph(f"<b>Date:</b> {issue_date}", meta_style),
        Paragraph(f"<b>Valid Until:</b> {valid_until}", meta_style),
    ]

    def para_cell(items):
        buf2 = io.BytesIO()
        return items  # will be used inline in table

    info_table = Table(
        [[from_block, to_block, details_block]],
        colWidths=[2.3 * inch, 2.3 * inch, 2.3 * inch],
    )
    info_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
        ("LINEAFTER", (0, 0), (1, -1), 0.5, colors.HexColor("#DDDDDD")),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.25 * inch))

    # ── Job Description ───────────────────────────────
    story.append(Paragraph(
        f"<b>Job Description:</b> {quote_data.get('job_description', '')}",
        ParagraphStyle("jobdesc", fontSize=10, leading=14, textColor=colors.HexColor("#333333"))
    ))
    story.append(Spacer(1, 0.2 * inch))

    # ── Line Items Table ───────────────────────────────
    col_headers = ["Description", "Detail", "Est. Low", "Est. High"]
    table_data = [
        [Paragraph(f"<b>{h}</b>", ParagraphStyle(
            "th", fontSize=9, textColor=WHITE, alignment=TA_CENTER if i > 1 else TA_LEFT
        )) for i, h in enumerate(col_headers)]
    ]

    line_item_style = ParagraphStyle("li", fontSize=9, leading=13)
    detail_style = ParagraphStyle("dt", fontSize=8, leading=12, textColor=MID_GRAY)

    for item in quote_data["line_items"]:
        table_data.append([
            Paragraph(f"<b>{item['description']}</b>", line_item_style),
            Paragraph(item["detail"], detail_style),
            Paragraph(f"${item['min']:,.0f}", ParagraphStyle("num", fontSize=9, alignment=TA_RIGHT)),
            Paragraph(f"${item['max']:,.0f}", ParagraphStyle("num", fontSize=9, alignment=TA_RIGHT)),
        ])

    # Total row
    table_data.append([
        Paragraph("<b>ESTIMATED TOTAL</b>", ParagraphStyle("tot", fontSize=10, textColor=WHITE)),
        Paragraph("", detail_style),
        Paragraph(
            f"<b>${quote_data['total_min']:,.0f}</b>",
            ParagraphStyle("totn", fontSize=10, textColor=WHITE, alignment=TA_RIGHT)
        ),
        Paragraph(
            f"<b>${quote_data['total_max']:,.0f}</b>",
            ParagraphStyle("totn", fontSize=10, textColor=WHITE, alignment=TA_RIGHT)
        ),
    ])

    items_table = Table(
        table_data,
        colWidths=[2.5 * inch, 2.3 * inch, 1.0 * inch, 1.0 * inch],
    )

    n_items = len(quote_data["line_items"])
    total_row = 1 + n_items  # 0=header, 1..n=items, n+1=total

    items_table.setStyle(TableStyle([
        # Header row
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TOPPADDING", (0, 0), (-1, 0), 10),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
        ("LEFTPADDING", (0, 0), (-1, 0), 8),
        ("RIGHTPADDING", (0, 0), (-1, 0), 8),
        # Item rows
        ("BACKGROUND", (0, 1), (-1, n_items), WHITE),
        ("ROWBACKGROUNDS", (0, 1), (-1, n_items), [WHITE, LIGHT_GRAY]),
        ("TOPPADDING", (0, 1), (-1, n_items), 8),
        ("BOTTOMPADDING", (0, 1), (-1, n_items), 8),
        ("LEFTPADDING", (0, 1), (-1, n_items), 8),
        ("RIGHTPADDING", (0, 1), (-1, n_items), 8),
        # Total row
        ("BACKGROUND", (0, total_row), (-1, total_row), ORANGE),
        ("TOPPADDING", (0, total_row), (-1, total_row), 10),
        ("BOTTOMPADDING", (0, total_row), (-1, total_row), 10),
        ("LEFTPADDING", (0, total_row), (-1, total_row), 8),
        ("RIGHTPADDING", (0, total_row), (-1, total_row), 8),
        # Grid lines
        ("LINEBELOW", (0, 0), (-1, n_items), 0.5, colors.HexColor("#DDDDDD")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 0.3 * inch))

    # ── Price Range Banner ─────────────────────────────
    story.append(HRFlowable(width="100%", thickness=2, color=ORANGE))
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph(
        f"Estimated Project Range: <b><font color='#FF6B00'>${quote_data['total_min']:,.0f} – ${quote_data['total_max']:,.0f}</font></b>",
        ParagraphStyle("range", fontSize=13, textColor=NAVY, alignment=TA_CENTER)
    ))
    story.append(Spacer(1, 0.1 * inch))
    story.append(HRFlowable(width="100%", thickness=2, color=ORANGE))
    story.append(Spacer(1, 0.25 * inch))

    # ── Terms ─────────────────────────────────────────
    terms_text = quote_data.get("terms") or (
        "This quote is valid for 30 days from the issue date. "
        "Final pricing may vary based on site conditions discovered during work. "
        "A 50% deposit is required to schedule. "
        "Payment in full due upon project completion. "
        "All work performed to local code standards."
    )
    story.append(Paragraph("<b>Terms & Conditions</b>", ParagraphStyle("th2", fontSize=10, textColor=NAVY)))
    story.append(Spacer(1, 0.05 * inch))
    story.append(Paragraph(terms_text, ParagraphStyle(
        "terms", fontSize=8, textColor=MID_GRAY, leading=13
    )))
    story.append(Spacer(1, 0.3 * inch))

    # ── Signature Block ────────────────────────────────
    sig_data = [[
        Paragraph("Contractor Signature: ____________________________", meta_style),
        Paragraph("Client Acceptance: ____________________________", meta_style),
    ]]
    sig_table = Table(sig_data, colWidths=[3.5 * inch, 3.5 * inch])
    sig_table.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(sig_table)

    # ── Footer ─────────────────────────────────────────
    def add_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MID_GRAY)
        footer_text = "Powered by QuoteBoss  •  quoteboss.io  •  Fast. Professional. Accurate."
        canvas.drawCentredString(letter[0] / 2, 0.4 * inch, footer_text)
        canvas.restoreState()

    doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
    buf.seek(0)
    return buf.read()


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", pricing=json.dumps(PRICING))


@app.route("/api/quote", methods=["POST"])
def api_quote():
    data = request.get_json(force=True)
    try:
        calc = calculate_quote(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    quote_id = str(uuid.uuid4())[:8].upper()
    quote_record = {
        "quote_id": quote_id,
        "contractor_name": data.get("contractor_name", ""),
        "contractor_business": data.get("contractor_business", ""),
        "contractor_phone": data.get("contractor_phone", ""),
        "contractor_email": data.get("contractor_email", ""),
        "client_name": data.get("client_name", ""),
        "client_address": data.get("client_address", ""),
        "location": data.get("location", ""),
        "trade": data.get("trade", ""),
        "job_type": data.get("job_type", ""),
        "job_description": data.get("job_description", ""),
        "property_size": data.get("property_size", 1500),
        "labor_hours": data.get("labor_hours", 4),
        "materials": data.get("materials", []),
        "terms": data.get("terms", ""),
        "line_items": calc["line_items"],
        "total_min": calc["total_min"],
        "total_max": calc["total_max"],
        "multiplier": calc["multiplier"],
        "state": calc["state"],
    }

    quote_store[quote_id] = quote_record

    return jsonify({
        "quote_id": quote_id,
        "line_items": calc["line_items"],
        "total_min": calc["total_min"],
        "total_max": calc["total_max"],
        "state": calc["state"],
        "multiplier": calc["multiplier"],
    })


@app.route("/api/pdf/<quote_id>", methods=["GET"])
def api_pdf(quote_id):
    quote = quote_store.get(quote_id.upper())
    if not quote:
        abort(404)
    pdf_bytes = generate_pdf(quote)
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"quote-{quote_id}.pdf",
    )


@app.route("/q/<quote_id>")
def view_quote(quote_id):
    quote = quote_store.get(quote_id.upper())
    if not quote:
        return render_template("index.html", pricing=json.dumps(PRICING), error="Quote not found or expired.")
    return render_template("index.html", pricing=json.dumps(PRICING), shared_quote=json.dumps(quote))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
