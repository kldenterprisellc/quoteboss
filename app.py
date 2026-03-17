import os
import io
import json
import json as json_module
import smtplib
from email.mime.text import MIMEText
import stripe

stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
PLATFORM_ACCOUNT_ID = 'acct_1JkUcCA2yPglm08v'
import uuid
import base64
import hashlib
import secrets
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, send_file, abort, redirect, session
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from database import (
    init_db, get_contractor, upsert_contractor, save_quote, get_quote,
    init_feedback_table, save_feedback, get_all_feedback,
    record_quote_view, get_quote_views_batch, accept_quote
)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or os.urandom(32)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max upload
init_db()
init_feedback_table()

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# In-memory quote store (backed by SQLite for persistence across restarts)
quote_store = {}

# ─────────────────────────────────────────────
# Pricing data
# ─────────────────────────────────────────────
PRICING = {
    "HVAC": {
        # Sources: HVAC.com 2025, Thumbtack 2025, JackLehr 2025, Modernize 2026
        # NOTE: All "job" prices = TOTAL installed (labor + equipment). No separate labor added.
        "AC Install (Central)":  {"min": 4000, "max": 9000,  "unit": "job"},
        "Full HVAC System":      {"min": 10000,"max": 20000, "unit": "job"},
        "AC Repair":             {"min": 150,  "max": 650,   "unit": "job"},
        "Furnace Install":       {"min": 3000, "max": 7500,  "unit": "job"},
        "Furnace Repair":        {"min": 130,  "max": 600,   "unit": "job"},
        "Duct Cleaning":         {"min": 300,  "max": 750,   "unit": "job"},
        "Mini Split Install":    {"min": 2500, "max": 8000,  "unit": "job"},
    },
    "Plumbing": {
        # Sources: ThisOldHouse 2025, AllStatePlumbing 2025, HomeAdvisor 2025, Angi 2026
        # NOTE: All "job" prices = TOTAL installed (labor + parts). No separate labor added.
        "Water Heater (Tank)":    {"min": 1000, "max": 3500,  "unit": "job"},
        "Water Heater (Tankless)":{"min": 2500, "max": 6000,  "unit": "job"},
        "Pipe Repair":            {"min": 150,  "max": 600,   "unit": "job"},
        "Drain Cleaning":         {"min": 100,  "max": 550,   "unit": "job"},
        "Bathroom Remodel (Plumbing)":{"min": 2500, "max": 8000, "unit": "job"},
        "Sewer Line Repair":      {"min": 1000, "max": 7500,  "unit": "job"},
        "Faucet/Fixture Install": {"min": 150,  "max": 500,   "unit": "job"},
    },
    "Electrical": {
        # Sources: SartellElectrical 2025, PanelLoadCalc 2025, HomeWyse 2026, Angi 2025
        # NOTE: All "job" prices = TOTAL installed (labor + materials + permit). No separate labor added.
        "Panel Upgrade":          {"min": 1500, "max": 4500,  "unit": "job"},
        "Outlet Install":         {"min": 150,  "max": 400,   "unit": "job"},
        "Lighting Install":       {"min": 150,  "max": 600,   "unit": "job"},
        "Ceiling Fan Install":    {"min": 100,  "max": 350,   "unit": "job"},
        "EV Charger (Level 2)":   {"min": 750,  "max": 2500,  "unit": "job"},
        "Whole Home Rewire":      {"min": 8000, "max": 25000, "unit": "job"},
        "Generator Install":      {"min": 3500, "max": 12000, "unit": "job"},
    },
    "Roofing": {
        # Sources: BillRagan 2025, RidgetopExteriors 2026, CMBRoof 2025
        # Per-sq prices = TOTAL installed (shingles + labor + tear-off). Separate labor added for repairs only.
        "Full Replacement (Asphalt)": {"min": 550, "max": 950, "unit": "per sq (100 sqft)"},
        "Full Replacement (Metal)":   {"min": 900, "max": 1800,"unit": "per sq (100 sqft)"},
        "Repair (Minor)":             {"min": 200, "max": 700, "unit": "job"},
        "Repair (Major)":             {"min": 700, "max": 3000,"unit": "job"},
        "Gutter Install/Replace":     {"min": 1500,"max": 5500,"unit": "job"},
        "Skylight Install":           {"min": 1000, "max": 4000,"unit": "job"},
    },
    "Landscaping": {
        # Sources: Angi 2026, HomeAdvisor 2025, HomeGuide 2025
        "Lawn Maintenance (Monthly)": {"min": 100, "max": 350,  "unit": "per month"},
        "Sod Installation":           {"min": 1.5, "max": 3.5,  "unit": "per sqft"},
        "Tree Removal (Small)":       {"min": 300, "max": 900,  "unit": "job"},
        "Tree Removal (Large)":       {"min": 900, "max": 3500, "unit": "job"},
        "Sprinkler System Install":   {"min": 2500,"max": 7000, "unit": "job"},
        "Full Landscape Design":      {"min": 3000,"max": 15000,"unit": "job"},
    },
    "General": {
        # Sources: HomeAdvisor 2025, HomeWyse 2026
        "Handyman (Per Hour)":    {"min": 75,  "max": 200,  "unit": "per hour"},
        "Interior Painting":      {"min": 2.00,"max": 6.00, "unit": "per sqft"},
        "Exterior Painting":      {"min": 2.20,"max": 5.00, "unit": "per sqft"},
        "Flooring Install":       {"min": 4,   "max": 14,   "unit": "per sqft"},
        "Drywall Repair":         {"min": 250, "max": 900,  "unit": "job"},
        "Deck Build":             {"min": 6000,"max": 20000,"unit": "job"},
    },
    "Pressure Washing": {
        # Sources: Thumbtack 2025, TaskRabbit 2025, InvoiceFly 2025, HomeGuide 2026
        # Per-sqft prices = total (labor included). No separate labor added.
        "House Exterior Wash":      {"min": 0.25, "max": 0.55, "unit": "per sqft"},
        "Driveway Cleaning":        {"min": 100,  "max": 350,  "unit": "job"},
        "Deck or Patio":            {"min": 0.25, "max": 0.50, "unit": "per sqft"},
        "Roof Soft Wash":           {"min": 350,  "max": 800,  "unit": "job"},
        "Fence Cleaning":           {"min": 100,  "max": 400,  "unit": "job"},
        "Commercial Building":      {"min": 0.20, "max": 0.55, "unit": "per sqft"},
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

LABOR_DEFAULTS = {
    # "job" unit types: prices already include labor, so labor_hours = 0
    # "per sqft"/"per sq" types: labor is on top of materials rate
    "HVAC": {
        "AC Install (Central)": 0,   # total job price includes install labor
        "Full HVAC System": 0,        # total job price includes install labor
        "AC Repair": 0,
        "Furnace Install": 0,
        "Furnace Repair": 0,
        "Duct Cleaning": 0,
        "Mini Split Install": 0,
    },
    "Plumbing": {
        "Water Heater (Tank)": 0,     # total installed price
        "Water Heater (Tankless)": 0,
        "Pipe Repair": 0,
        "Drain Cleaning": 0,
        "Bathroom Remodel (Plumbing)": 0,
        "Sewer Line Repair": 0,
        "Faucet/Fixture Install": 0,
    },
    "Electrical": {
        "Panel Upgrade": 0,           # total installed price includes permit + labor
        "Outlet Install": 0,
        "Lighting Install": 0,
        "Ceiling Fan Install": 0,
        "EV Charger (Level 2)": 0,
        "Whole Home Rewire": 0,
        "Generator Install": 0,
    },
    "Roofing": {
        "Full Replacement (Asphalt)": 0,  # per-sq rate includes tear-off + labor
        "Full Replacement (Metal)": 0,
        "Repair (Minor)": 2,              # repairs: add labor on top of parts
        "Repair (Major)": 5,
        "Gutter Install/Replace": 4,
        "Skylight Install": 4,
    },
    "Landscaping": {
        "Lawn Maintenance (Monthly)": 0,
        "Sod Installation": 0,            # per-sqft rate includes labor
        "Tree Removal (Small)": 0,
        "Tree Removal (Large)": 0,
        "Sprinkler System Install": 0,
        "Full Landscape Design": 0,
    },
    "General": {
        "Handyman (Per Hour)": 0,         # IS labor, no separate labor line
        "Interior Painting": 0,           # per-sqft rate includes labor
        "Exterior Painting": 0,           # per-sqft rate includes labor
        "Flooring Install": 0,            # per-sqft rate includes labor
        "Drywall Repair": 0,
        "Deck Build": 0,
    },
}

LABOR_RATE = 85  # $ per hour base (default)

# Per-trade labor rates (national averages 2025)
TRADE_LABOR_RATES = {
    "Roofing":          65,
    "HVAC":             95,
    "Plumbing":         90,
    "Electrical":       95,
    "Painting":         55,
    "Pressure Washing": 60,
    "Landscaping":      50,
    "General":          75,
}


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

    # Custom pricing override
    custom_min = data.get("custom_min") if data.get("custom_min") is not None else data.get("custom_price_min")
    custom_max = data.get("custom_max") if data.get("custom_max") is not None else data.get("custom_price_max")
    using_custom = False
    if custom_min is not None and custom_max is not None:
        try:
            custom_min = float(custom_min)
            custom_max = float(custom_max)
            if custom_min > 0 and custom_max >= custom_min:
                using_custom = True
        except (TypeError, ValueError):
            pass

    unit = pricing["unit"]
    if using_custom:
        base_min = custom_min
        base_max = custom_max
        multiplier = 1.0
    else:
        base_min = pricing["min"]
        base_max = pricing["max"]

    if not using_custom:
        if "sqft" in unit:
            base_min = base_min * property_size
            base_max = base_max * property_size
        elif "per sq" in unit:
            # Roofing "squares" = 100 sqft
            squares = property_size / 100
            base_min = base_min * squares
            base_max = base_max * squares

        base_min = base_min * multiplier
        base_max = base_max * multiplier

    trade_rate = TRADE_LABOR_RATES.get(trade, LABOR_RATE)
    labor_min = labor_hours * trade_rate * 0.9
    labor_max = labor_hours * trade_rate * 1.1

    # Job prices already include materials -- no auto-add
    # Custom materials are handled as custom line items only
    materials_min = materials_max = 0
    total_min = base_min + labor_min
    total_max = base_max + labor_max

    def r50(v):
        return round(v / 50) * 50

    base_detail = "Your custom rate" if using_custom else f"Estimated total ({unit})"

    line_items = [
        {
            "description": f"{job_type} - {trade} Service",
            "detail": base_detail,
            "min": r50(base_min),
            "max": r50(base_max),
        },
    ]
    # Only add a separate labor line when labor_hours > 0
    # (for "job" unit types, labor is already included in the base price)
    if labor_hours > 0:
        line_items.append({
            "description": "Labor",
            "detail": f"{labor_hours:.1f} hrs @ ${trade_rate}/hr",
            "min": r50(labor_min),
            "max": r50(labor_max),
        })

    # Roofing tear-off surcharge
    include_tearoff = data.get('include_tearoff', False)
    roof_squares = data.get('roof_squares', 0)
    if include_tearoff and roof_squares and trade == 'Roofing':
        tearoff_min = float(roof_squares) * 150
        tearoff_max = float(roof_squares) * 200
        line_items.append({
            "description": "Tear-off and Disposal",
            "detail": f"Remove existing roof ({roof_squares} squares)",
            "min": r50(tearoff_min),
            "max": r50(tearoff_max),
        })
        total_min += tearoff_min
        total_max += tearoff_max

    return {
        "line_items": line_items,
        "total_min": r50(total_min),
        "total_max": r50(total_max),
        "multiplier": multiplier,
        "state": state,
        "unit": unit,
        "using_custom_pricing": using_custom,
    }


def calculate_multi_scope_quote(data: dict, job_types: list) -> dict:
    """Calculate a combined quote for multiple scopes of work.
    Labor lines are merged into a single combined labor line."""
    non_labor_items = []
    total_labor_min = 0
    total_labor_max = 0
    total_labor_hours = 0
    total_min = 0
    total_max = 0
    last_result = None
    trade = data.get("trade", "General")
    trade_rate = TRADE_LABOR_RATES.get(trade, LABOR_RATE)

    # If contractor provided explicit total hours, use that for combined labor
    override_hours = data.get("job_hours")

    for jt in job_types:
        scope_data = dict(data)
        scope_data["job_type"] = jt
        try:
            result = calculate_quote(scope_data)
        except ValueError:
            continue
        items = result["line_items"]
        for item in items:
            if item["description"] == "Labor":
                total_labor_min += item["min"]
                total_labor_max += item["max"]
                # Parse hours from detail string
                try:
                    total_labor_hours += float(item["detail"].split(" hrs")[0])
                except Exception:
                    pass
            else:
                # Label base line with scope name
                if "Service" in item.get("description", ""):
                    item["description"] = f"{jt} - {item['description'].split(' - ')[-1]}"
                non_labor_items.append(item)
        total_min += result["total_min"]
        total_max += result["total_max"]
        last_result = result

    if not last_result:
        raise ValueError("No valid job types found")

    # If contractor entered explicit hours, recalculate labor from scratch
    if override_hours and float(override_hours) > 0:
        hrs = float(override_hours)
        total_labor_min = hrs * trade_rate * 0.9
        total_labor_max = hrs * trade_rate * 1.1
        total_labor_hours = hrs
        # Recalc totals: non-labor base + new labor
        base_min = sum(i["min"] for i in non_labor_items if "Materials" not in i["description"])
        base_max = sum(i["max"] for i in non_labor_items if "Materials" not in i["description"])
        mat_min = sum(i["min"] for i in non_labor_items if "Materials" in i["description"])
        mat_max = sum(i["max"] for i in non_labor_items if "Materials" in i["description"])
        total_min = base_min + total_labor_min + mat_min
        total_max = base_max + total_labor_max + mat_max

    def r50(v):
        return round(v / 50) * 50

    # Single combined labor line
    combined_labor = {
        "description": "Labor (Combined)",
        "detail": f"{total_labor_hours:.1f} hrs total @ ${trade_rate}/hr",
        "min": r50(total_labor_min),
        "max": r50(total_labor_max),
    }

    # Non-labor items (base lines + materials), then one labor line at end
    all_items = non_labor_items + [combined_labor]

    return {
        "line_items": all_items,
        "total_min": r50(total_min),
        "total_max": r50(total_max),
        "multiplier": last_result.get("multiplier", 1.0),
        "state": last_result.get("state", ""),
        "unit": last_result.get("unit", "job"),
        "using_custom_pricing": last_result.get("using_custom_pricing", False),
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

    story.append(Paragraph(
        f"<b>Job Description:</b> {quote_data.get('job_description', '')}",
        ParagraphStyle("jobdesc", fontSize=10, leading=14, textColor=colors.HexColor("#333333"))
    ))
    story.append(Spacer(1, 0.2 * inch))

    final_price = quote_data.get('final_price')
    is_client_facing = bool(final_price)

    line_item_style = ParagraphStyle("li", fontSize=9, leading=13)
    detail_style = ParagraphStyle("dt", fontSize=8, leading=12, textColor=MID_GRAY)

    if is_client_facing:
        col_headers = ["Description", "Detail", "Price"]
        table_data = [
            [Paragraph(f"<b>{h}</b>", ParagraphStyle(
                "th", fontSize=9, textColor=WHITE, alignment=TA_RIGHT if i == 2 else TA_LEFT
            )) for i, h in enumerate(col_headers)]
        ]
        base_total = quote_data.get('total_max') or quote_data.get('total_min') or 1
        scale = final_price / base_total if base_total else 1
        for item in quote_data["line_items"]:
            item_price = round(item['max'] * scale)
            # Hide hourly rate from client PDF -- show hours only
            raw_detail = item.get("detail", "")
            if ' @ $' in raw_detail and '/hr' in raw_detail:
                raw_detail = raw_detail.split(' @ $')[0]
            table_data.append([
                Paragraph(f"<b>{item['description']}</b>", line_item_style),
                Paragraph(raw_detail, detail_style),
                Paragraph(f"${item_price:,.0f}", ParagraphStyle("num", fontSize=9, alignment=TA_RIGHT)),
            ])
        for cli in quote_data.get('custom_line_items', []):
            table_data.append([
                Paragraph(f"<b>{cli['description']}</b>", line_item_style),
                Paragraph(f"{cli['markup_pct']}% markup" if cli.get('markup_pct') else "", detail_style),
                Paragraph(f"${cli['total']:,.0f}", ParagraphStyle("num", fontSize=9, alignment=TA_RIGHT)),
            ])
        if quote_data.get('discount_amount') and quote_data['discount_amount'] > 0:
            table_data.append([
                Paragraph("<b>Discount</b>", ParagraphStyle("disc", fontSize=9, leading=13, textColor=colors.HexColor("#2e7d32"))),
                Paragraph("", detail_style),
                Paragraph(f"-${quote_data['discount_amount']:,.0f}", ParagraphStyle("discn", fontSize=9, alignment=TA_RIGHT, textColor=colors.HexColor("#2e7d32"))),
            ])
        table_data.append([
            Paragraph("<b>QUOTE TOTAL</b>", ParagraphStyle("tot", fontSize=10, textColor=WHITE)),
            Paragraph("", detail_style),
            Paragraph(f"<b>${final_price:,.0f}</b>", ParagraphStyle("totn", fontSize=10, textColor=WHITE, alignment=TA_RIGHT)),
        ])
        items_table = Table(table_data, colWidths=[2.5 * inch, 2.8 * inch, 1.5 * inch])
    else:
        col_headers = ["Description", "Detail", "Est. Low", "Est. High"]
        table_data = [
            [Paragraph(f"<b>{h}</b>", ParagraphStyle(
                "th", fontSize=9, textColor=WHITE, alignment=TA_CENTER if i > 1 else TA_LEFT
            )) for i, h in enumerate(col_headers)]
        ]
        for item in quote_data["line_items"]:
            raw_detail2 = item.get("detail", "")
            if ' @ $' in raw_detail2 and '/hr' in raw_detail2:
                raw_detail2 = raw_detail2.split(' @ $')[0]
            table_data.append([
                Paragraph(f"<b>{item['description']}</b>", line_item_style),
                Paragraph(raw_detail2, detail_style),
                Paragraph(f"${item['min']:,.0f}", ParagraphStyle("num", fontSize=9, alignment=TA_RIGHT)),
                Paragraph(f"${item['max']:,.0f}", ParagraphStyle("num", fontSize=9, alignment=TA_RIGHT)),
            ])
        table_data.append([
            Paragraph("<b>ESTIMATED TOTAL</b>", ParagraphStyle("tot", fontSize=10, textColor=WHITE)),
            Paragraph("", detail_style),
            Paragraph(f"<b>${quote_data['total_min']:,.0f}</b>", ParagraphStyle("totn", fontSize=10, textColor=WHITE, alignment=TA_RIGHT)),
            Paragraph(f"<b>${quote_data['total_max']:,.0f}</b>", ParagraphStyle("totn", fontSize=10, textColor=WHITE, alignment=TA_RIGHT)),
        ])
        items_table = Table(table_data, colWidths=[2.5 * inch, 2.3 * inch, 1.0 * inch, 1.0 * inch])

    n_base_items = len(quote_data["line_items"])
    n_custom = len(quote_data.get('custom_line_items', []))
    has_discount = bool(quote_data.get('discount_amount') and quote_data['discount_amount'] > 0 and is_client_facing)
    n_items = n_base_items + n_custom + (1 if has_discount else 0)
    total_row = 1 + n_items

    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TOPPADDING", (0, 0), (-1, 0), 10),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
        ("LEFTPADDING", (0, 0), (-1, 0), 8),
        ("RIGHTPADDING", (0, 0), (-1, 0), 8),
        ("BACKGROUND", (0, 1), (-1, n_items), WHITE),
        ("ROWBACKGROUNDS", (0, 1), (-1, n_items), [WHITE, LIGHT_GRAY]),
        ("TOPPADDING", (0, 1), (-1, n_items), 8),
        ("BOTTOMPADDING", (0, 1), (-1, n_items), 8),
        ("LEFTPADDING", (0, 1), (-1, n_items), 8),
        ("RIGHTPADDING", (0, 1), (-1, n_items), 8),
        ("BACKGROUND", (0, total_row), (-1, total_row), ORANGE),
        ("TOPPADDING", (0, total_row), (-1, total_row), 10),
        ("BOTTOMPADDING", (0, total_row), (-1, total_row), 10),
        ("LEFTPADDING", (0, total_row), (-1, total_row), 8),
        ("RIGHTPADDING", (0, total_row), (-1, total_row), 8),
        ("LINEBELOW", (0, 0), (-1, n_items), 0.5, colors.HexColor("#DDDDDD")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 0.3 * inch))

    final_price = quote_data.get('final_price')
    if final_price:
        total_display = f"${final_price:,.0f}"
        price_label = "Project Quote"
    else:
        total_display = f"${quote_data['total_min']:,.0f} - ${quote_data['total_max']:,.0f}"
        price_label = "Estimated Project Range"
    story.append(HRFlowable(width="100%", thickness=2, color=ORANGE))
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph(
        f"{price_label}: <b><font color='#FF6B00'>{total_display}</font></b>",
        ParagraphStyle("range", fontSize=13, textColor=NAVY, alignment=TA_CENTER)
    ))
    story.append(Spacer(1, 0.1 * inch))
    story.append(HRFlowable(width="100%", thickness=2, color=ORANGE))
    story.append(Spacer(1, 0.25 * inch))

    terms_text = quote_data.get("terms") or (
        "This quote is valid for 30 days from the issue date. "
        "Final pricing may vary based on site conditions discovered during work. "
        "A 50% deposit is required to schedule. "
        "Payment in full due upon project completion. "
        "All work performed to local code standards."
    )
    story.append(Paragraph("<b>Terms and Conditions</b>", ParagraphStyle("th2", fontSize=10, textColor=NAVY)))
    story.append(Spacer(1, 0.05 * inch))
    story.append(Paragraph(terms_text, ParagraphStyle(
        "terms", fontSize=8, textColor=MID_GRAY, leading=13
    )))
    story.append(Spacer(1, 0.3 * inch))

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

    def add_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MID_GRAY)
        footer_text = "Powered by QuoteBoss  |  quoteboss.io  |  Fast. Professional. Accurate."
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
    if not session.get('whop_user_id'):
        return redirect('/access')
    tier = session.get('plan_tier', 'basic')
    contractor = get_contractor(session['whop_user_id']) or {}
    all_trades_raw = contractor.get('all_trades', '') or ''
    all_trades_list = [t.strip() for t in all_trades_raw.split(',') if t.strip()]
    single_trade_mode = len(all_trades_list) == 1
    return render_template(
        "index.html",
        pricing=json.dumps(PRICING),
        plan_tier=tier,
        contractor=contractor,
        primary_trade=contractor.get('primary_trade', ''),
        all_trades=all_trades_list,
        single_trade_mode=single_trade_mode
    )


@app.route("/access")
def access_page():
    if session.get('whop_user_id'):
        return redirect('/')
    error = request.args.get('error', '')
    return render_template("access.html", error=error)


@app.route("/onboarding", methods=["GET", "POST"])
def onboarding():
    if not session.get('whop_user_id'):
        return redirect('/access')
    contractor = get_contractor(session['whop_user_id']) or {}
    if contractor.get('business_name'):
        return redirect('/')

    if request.method == 'POST':
        logo_url = ''
        if 'logo' in request.files:
            logo_file = request.files['logo']
            if logo_file and logo_file.filename:
                uploads_dir = os.path.join(app.root_path, 'static', 'uploads')
                os.makedirs(uploads_dir, exist_ok=True)
                ext = 'png'
                if '.' in logo_file.filename:
                    ext = logo_file.filename.rsplit('.', 1)[-1].lower()
                filename = f"{session['whop_user_id']}_logo.{ext}"
                logo_file.save(os.path.join(uploads_dir, filename))
                logo_url = f"/static/uploads/{filename}"

        update_fields = {
            'business_name': request.form.get('business_name', '').strip(),
            'owner_name': request.form.get('owner_name', '').strip(),
            'phone': request.form.get('phone', '').strip(),
            'email': request.form.get('email', '').strip(),
            'city_state': request.form.get('city_state', '').strip(),
            'primary_trade': request.form.get('primary_trade', '').strip(),
            'team_size': request.form.get('team_size', '').strip(),
            'all_trades': request.form.get('all_trades', '').strip(),
            'payment_methods': request.form.get('payment_methods', 'cash,check,venmo').strip(),
            'zelle_handle': request.form.get('zelle_handle', '').strip(),
        }
        if logo_url:
            update_fields['logo_url'] = logo_url

        upsert_contractor(session['whop_user_id'], **update_fields)
        return redirect('/')

    return render_template('onboarding.html')


@app.route("/auth/login")
@limiter.limit("10 per minute")
def auth_login():
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=').decode()
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b'=').decode()
    state = secrets.token_urlsafe(16)
    nonce = secrets.token_urlsafe(16)

    session['pkce_verifier'] = code_verifier
    session['oauth_state'] = state
    session['oauth_nonce'] = nonce

    redirect_uri = "https://quoteboss.io/auth/callback"

    params = urllib.parse.urlencode({
        'response_type': 'code',
        'client_id': 'app_VOH7DioBCcAGsp',
        'redirect_uri': redirect_uri,
        'scope': 'openid profile email',
        'state': state,
        'nonce': nonce,
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256',
    })
    return redirect(f'https://api.whop.com/oauth/authorize?{params}')


@app.route("/auth/callback")
@limiter.limit("10 per minute")
def auth_callback():
    error = request.args.get('error')
    if error:
        return redirect('/access?error=' + urllib.parse.quote(error))

    code = request.args.get('code')
    state = request.args.get('state')

    if state != session.get('oauth_state'):
        return redirect('/access?error=invalid_state')

    code_verifier = session.pop('pkce_verifier', None)
    session.pop('oauth_state', None)

    if not code_verifier:
        return redirect('/access?error=missing_verifier')

    redirect_uri = "https://quoteboss.io/auth/callback"

    try:
        token_data = urllib.parse.urlencode({
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri,
            'client_id': 'app_VOH7DioBCcAGsp',
            'code_verifier': code_verifier,
        }).encode()

        token_req = urllib.request.Request(
            'https://api.whop.com/oauth/token',
            data=token_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            method='POST'
        )
        with urllib.request.urlopen(token_req, timeout=10) as r:
            tokens = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='ignore')
        print(f"[OAuth] token exchange HTTPError {e.code}: {body}", flush=True)
        return redirect('/access?error=token_failed')
    except Exception as e:
        print(f"[OAuth] token exchange error: {e}", flush=True)
        return redirect('/access?error=token_failed')

    access_token = tokens.get('access_token')
    if not access_token:
        return redirect('/access?error=no_token')

    try:
        user_req = urllib.request.Request(
            'https://api.whop.com/api/v2/me',
            headers={'Authorization': f'Bearer {access_token}'}
        )
        with urllib.request.urlopen(user_req, timeout=10) as r:
            user_info = json.loads(r.read())
        user_id = user_info.get('id') or user_info.get('user', {}).get('id')
    except Exception:
        return redirect('/access?error=user_fetch_failed')

    WHOP_API_KEY = os.environ.get('WHOP_API_KEY', '')
    try:
        mem_req = urllib.request.Request(
            f'https://api.whop.com/api/v2/memberships?product_id=prod_Bunxdbxo96qpc&valid=true&user_id={user_id}',
            headers={'Authorization': f'Bearer {WHOP_API_KEY}'}
        )
        with urllib.request.urlopen(mem_req, timeout=10) as r:
            mem_data = json.loads(r.read())
    except Exception:
        return redirect('/access?error=membership_check_failed')

    # Owner bypass
    OWNER_USER_ID = 'user_rYGUC3pFlNEz5'
    if user_id == OWNER_USER_ID:
        session['whop_user_id'] = user_id
        session['plan_tier'] = 'pro'
        session['access_token'] = access_token
        session.permanent = True
        contractor = get_contractor(user_id) or {}
        if not contractor.get('business_name'):
            return redirect('/onboarding')
        return redirect('/')

    memberships = mem_data.get('data', [])
    active = [m for m in memberships if m.get('status') == 'active']

    if not active:
        return redirect('/access?error=no_membership')

    membership = active[0]
    plan_id = membership.get('plan_id', '')
    tier = 'pro' if plan_id == 'plan_v5y4UTJONBPVB' else 'basic'

    session['whop_user_id'] = user_id
    session['plan_tier'] = tier
    session['access_token'] = access_token
    session.permanent = True

    # Redirect to onboarding if no business name set
    contractor = get_contractor(user_id) or {}
    if not contractor.get('business_name'):
        return redirect('/onboarding')
    return redirect('/')


@app.route("/auth/owner-login")
def owner_login():
    """Direct owner bypass."""
    secret = request.args.get('secret', '')
    expected = os.environ.get('OWNER_LOGIN_SECRET', '')
    if not expected or secret != expected:
        return redirect('/access?error=unauthorized')
    session['whop_user_id'] = 'user_rYGUC3pFlNEz5'
    session['plan_tier'] = 'pro'
    session.permanent = True
    contractor = get_contractor('user_rYGUC3pFlNEz5') or {}
    if not contractor.get('business_name'):
        return redirect('/onboarding')
    return redirect('/')


@app.route("/admin/reset-onboarding")
def reset_onboarding():
    """Clear onboarding data for logged-in user so they can redo it."""
    if session.get('whop_user_id') != 'user_rYGUC3pFlNEz5':
        return redirect('/access?error=unauthorized')
    uid = session['whop_user_id']
    upsert_contractor(uid, business_name='', primary_trade='', all_trades='')
    return redirect('/onboarding')


@app.route("/logout")
def logout():
    session.clear()
    return redirect('/access')


@app.route("/api/labor-defaults", methods=["GET"])
def api_labor_defaults():
    return jsonify(LABOR_DEFAULTS)


def _apply_trade_multiplier(calc, multiplier):
    """Apply a post-calculation multiplier to all line items and totals."""
    if multiplier == 1.0:
        return calc

    def r50(v):
        return round(v / 50) * 50

    for item in calc['line_items']:
        item['min'] = r50(item['min'] * multiplier)
        item['max'] = r50(item['max'] * multiplier)

    calc['total_min'] = r50(calc['total_min'] * multiplier)
    calc['total_max'] = r50(calc['total_max'] * multiplier)
    return calc


@app.route("/api/quote", methods=["POST"])
@limiter.limit("30 per minute")
def api_quote():
    if not session.get('whop_user_id'):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True)

    # Remap Painting trade to General for PRICING lookup
    original_trade = data.get('trade', '')
    if original_trade == 'Painting':
        data['trade'] = 'General'

    # Apply trade_multiplier after calculation (pitch, size, prep, etc.)
    trade_multiplier = float(data.pop('trade_multiplier', 1.0) or 1.0)

    # Support multiple scopes of work
    job_types = data.get('job_types', [])
    if isinstance(job_types, list) and len(job_types) > 1:
        try:
            calc = calculate_multi_scope_quote(data, job_types)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
    else:
        try:
            calc = calculate_quote(data)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    # Apply trade-specific multiplier
    if trade_multiplier != 1.0:
        calc = _apply_trade_multiplier(calc, trade_multiplier)

    # Restore original trade label for display
    data['trade'] = original_trade

    quote_id = str(uuid.uuid4())[:8].upper()
    quote_record = {
        "quote_id": quote_id,
        "whop_user_id": session.get('whop_user_id', ''),
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
        "custom_price_min": data.get("custom_price_min"),
        "custom_price_max": data.get("custom_price_max"),
        "using_custom_pricing": calc["using_custom_pricing"],
        "line_items": calc["line_items"],
        "total_min": calc["total_min"],
        "total_max": calc["total_max"],
        "multiplier": calc["multiplier"],
        "state": calc["state"],
    }

    # Custom line items
    custom_line_items = data.get('line_items_custom', [])
    custom_line_items_total = 0
    processed_line_items = []
    for item in custom_line_items:
        if item.get('description') and item.get('amount', 0) > 0:
            base = float(item['amount'])
            markup_pct = float(item.get('markup', 0))
            markup_amt = base * (markup_pct / 100) if markup_pct else 0
            item_total = base + markup_amt
            custom_line_items_total += item_total
            processed_line_items.append({
                'description': item['description'],
                'amount': round(base),
                'markup_pct': markup_pct,
                'markup_amt': round(markup_amt),
                'total': round(item_total)
            })

    quote_record['custom_line_items'] = processed_line_items
    quote_record['custom_line_items_total'] = round(custom_line_items_total)
    quote_record['total_min'] += round(custom_line_items_total)
    quote_record['total_max'] += round(custom_line_items_total)

    # Discount
    discount_flat = float(data.get('discount_flat', 0) or 0)
    discount_pct = float(data.get('discount_pct', 0) or 0)

    discount_amount = 0
    if discount_flat > 0:
        discount_amount += discount_flat
    if discount_pct > 0:
        after_flat = quote_record['total_min'] - discount_flat
        discount_amount += after_flat * (discount_pct / 100)

    discount_amount = round(discount_amount)
    quote_record['discount_flat'] = round(discount_flat)
    quote_record['discount_pct'] = discount_pct
    quote_record['discount_amount'] = discount_amount
    quote_record['total_min'] = max(0, quote_record['total_min'] - discount_amount)
    quote_record['total_max'] = max(0, quote_record['total_max'] - discount_amount)

    final_price = round((quote_record['total_min'] + quote_record['total_max']) / 2)
    quote_record['final_price'] = final_price
    quote_record['final_price_set'] = False

    save_quote(quote_id, session.get('whop_user_id', ''), json_module.dumps(quote_record))
    quote_store[quote_id] = quote_record

    return jsonify({
        "quote_id": quote_id,
        "line_items": calc["line_items"],
        "total_min": quote_record['total_min'],
        "total_max": quote_record['total_max'],
        "final_price": final_price,
        "state": calc["state"],
        "multiplier": calc["multiplier"],
        "using_custom_pricing": calc["using_custom_pricing"],
    })


@app.route("/api/quote/set-price", methods=["POST"])
def set_quote_price():
    if not session.get('whop_user_id'):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True)
    quote_id = data.get('quote_id', '').upper()
    final_price = data.get('final_price')

    if not quote_id or not final_price:
        return jsonify({"error": "Missing quote_id or final_price"}), 400

    quote = quote_store.get(quote_id)
    db_quote = None
    if not quote:
        db_quote = get_quote(quote_id)
        if db_quote:
            quote = json_module.loads(db_quote['quote_data'])
    if not quote:
        return jsonify({"error": "Quote not found"}), 404

    # Ownership check: quote must belong to this user
    owner_id = quote.get('whop_user_id')
    if not owner_id and db_quote:
        owner_id = db_quote.get('whop_user_id')
    if owner_id and owner_id != session['whop_user_id']:
        return jsonify({"error": "Forbidden"}), 403

    quote['final_price'] = int(final_price)
    quote['final_price_set'] = True
    quote_store[quote_id] = quote

    save_quote(quote_id, session.get('whop_user_id', ''), json_module.dumps(quote))

    return jsonify({"success": True})


@app.route("/api/quote/accept/<quote_id>", methods=["POST"])
@limiter.limit("10 per minute")
def accept_quote_route(quote_id):
    """Public endpoint: client accepts a quote."""
    accept_quote(quote_id.upper())
    return jsonify({"success": True})


@app.route("/api/pdf/<quote_id>", methods=["GET"])
def api_pdf(quote_id):
    if not session.get('whop_user_id'):
        return jsonify({"error": "Unauthorized"}), 401
    quote = quote_store.get(quote_id.upper())
    db_quote = None
    if not quote:
        db_quote = get_quote(quote_id.upper())
        if db_quote:
            quote = json_module.loads(db_quote['quote_data'])
            quote_store[quote_id.upper()] = quote
    if not quote:
        abort(404)
    # Ownership check: only the contractor who created the quote can download its PDF
    owner_id = quote.get('whop_user_id')
    if not owner_id and db_quote:
        owner_id = db_quote.get('whop_user_id')
    if owner_id and owner_id != session['whop_user_id']:
        abort(403)
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
    whop_user_id = None
    db_row = None
    if not quote:
        db_row = get_quote(quote_id.upper())
        if db_row:
            quote = json_module.loads(db_row['quote_data'])
            quote_store[quote_id.upper()] = quote
            whop_user_id = db_row.get('whop_user_id')
    else:
        whop_user_id = quote.get('whop_user_id')
        db_row = get_quote(quote_id.upper())

    if not quote:
        tier = session.get('plan_tier', 'basic')
        return render_template("index.html", pricing=json.dumps(PRICING), plan_tier=tier, contractor={}, error="Quote not found or expired.")

    # Record the view
    try:
        record_quote_view(quote_id.upper(), request.remote_addr)
    except Exception:
        pass

    # Set accepted status from DB
    if db_row:
        quote['accepted'] = bool(db_row.get('accepted', 0))
        quote['accepted_at'] = db_row.get('accepted_at', '')
    else:
        quote['accepted'] = False

    contractor = get_contractor(whop_user_id) if whop_user_id else {}
    has_stripe = bool(contractor.get('stripe_account_id')) if contractor else False
    zelle_handle = contractor.get('zelle_handle', '') if contractor else ''
    fee_mode = 'pass_to_client'
    raw_methods = contractor.get('payment_methods', '') if contractor else ''
    accepted_methods = [m.strip() for m in raw_methods.split(',') if m.strip()] if raw_methods else ['cash', 'check', 'venmo']

    return render_template("quote_view.html", quote=quote, has_stripe=has_stripe, zelle_handle=zelle_handle, fee_mode=fee_mode, accepted_methods=accepted_methods)


@app.route("/settings")
def settings_page():
    if not session.get('whop_user_id'):
        return redirect('/access')
    contractor = get_contractor(session['whop_user_id']) or {}
    tier = session.get('plan_tier', 'basic')
    return render_template("settings.html", contractor=contractor, plan_tier=tier)


@app.route("/api/settings", methods=["POST"])
def update_settings():
    if not session.get('whop_user_id'):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True)

    allowed_fields = ['zelle_handle', 'fee_mode', 'payment_methods']
    updates = {k: v for k, v in data.items() if k in allowed_fields}

    if updates:
        upsert_contractor(session['whop_user_id'], **updates)

    return jsonify({"success": True})


@app.route("/admin/stripe-test")
def stripe_test():
    if session.get('whop_user_id') != 'user_rYGUC3pFlNEz5':
        return "unauthorized", 403
    import traceback
    results = []
    # Check DB columns
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='contractors' ORDER BY ordinal_position")
        cols = [r[0] for r in cur.fetchall()]
        conn.close()
        results.append(f"DB COLS: {cols}")
    except Exception as e:
        results.append(f"DB ERROR: {e}")
    # Test upsert
    try:
        upsert_contractor(session['whop_user_id'], stripe_account_id='test_acct_debug', stripe_onboarding_complete=0)
        results.append("UPSERT OK")
        upsert_contractor(session['whop_user_id'], stripe_account_id=None, stripe_onboarding_complete=None)
    except Exception as e:
        results.append(f"UPSERT ERROR: {traceback.format_exc()}")
    # Test full Stripe flow
    try:
        acct = stripe.Account.create(type='express', country='US',
            capabilities={'card_payments':{'requested':True},'transfers':{'requested':True}})
        link = stripe.AccountLink.create(
            account=acct.id,
            refresh_url='https://quoteboss.io/auth/stripe-connect',
            return_url='https://quoteboss.io/settings?stripe=success',
            type='account_onboarding',
        )
        stripe.Account.delete(acct.id)
        results.append(f"STRIPE OK: {acct.id}")
    except Exception as e:
        results.append(f"STRIPE ERROR: {traceback.format_exc()}")
    return "<br><br>".join(results)

@app.route("/auth/stripe-connect")
@limiter.limit("5 per minute")
def stripe_connect():
    if not session.get('whop_user_id'):
        return redirect('/access')

    try:
        account = stripe.Account.create(
            type='express',
            country='US',
            capabilities={
                'card_payments': {'requested': True},
                'transfers': {'requested': True},
            },
        )

        upsert_contractor(session['whop_user_id'], stripe_account_id=account.id, stripe_onboarding_complete=0)

        account_link = stripe.AccountLink.create(
            account=account.id,
            refresh_url='https://quoteboss.io/auth/stripe-connect',
            return_url='https://quoteboss.io/settings?stripe=success',
            type='account_onboarding',
        )

        return redirect(account_link.url)
    except Exception as e:
        import traceback
        print(f"[Stripe Connect Error] {e}")
        traceback.print_exc()
        return redirect('/settings?stripe=error')


@app.route("/api/create-checkout/<quote_id>", methods=["POST"])
@limiter.limit("20 per minute")
def create_checkout(quote_id):
    quote = quote_store.get(quote_id.upper())
    db_quote = None
    if not quote:
        db_quote = get_quote(quote_id.upper())
        if db_quote:
            quote = json_module.loads(db_quote['quote_data'])
    if not quote:
        return jsonify({"error": "Quote not found"}), 404

    whop_user_id = quote.get('whop_user_id')
    if not whop_user_id:
        if db_quote is None:
            db_quote = get_quote(quote_id.upper())
        whop_user_id = db_quote.get('whop_user_id') if db_quote else None

    contractor = get_contractor(whop_user_id) if whop_user_id else None
    if not contractor or not contractor.get('stripe_account_id'):
        return jsonify({"error": "Contractor has not connected Stripe"}), 400

    data = request.get_json(force=True)
    payment_type = data.get('payment_type', 'deposit')
    deposit_pct_override = data.get('deposit_pct')
    fixed_deposit_amt = quote.get('fixed_deposit_amt')

    quote_price = quote.get('final_price') or quote['total_max']

    if payment_type == 'full':
        total = quote_price
    elif payment_type == 'deposit':
        if fixed_deposit_amt:
            total = round(float(fixed_deposit_amt))
        elif deposit_pct_override:
            total = round(quote_price * int(deposit_pct_override) / 100)
        else:
            deposit_pct = quote.get('deposit_pct', 50)
            total = round(quote_price * (deposit_pct or 50) / 100)
    else:
        total = quote_price

    fee_mode = 'pass_to_client'

    if fee_mode == 'pass_to_client':
        client_total_cents = round(total * 1.01 * 100)
        application_fee_cents = round(total * 0.01 * 100)
    else:
        client_total_cents = round(total * 100)
        application_fee_cents = round(total * 0.01 * 100)

    job_desc = quote.get('job_description') or f"{quote.get('job_type', 'Job')} - {quote.get('trade', '')}"

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': f"{'50% Deposit' if payment_type == 'deposit' else 'Full Payment'} - {job_desc}",
                        'description': f"Quote #{quote_id} from {quote.get('contractor_business', 'Contractor')}",
                    },
                    'unit_amount': client_total_cents,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=f"https://quoteboss.io/q/{quote_id}?paid=true",
            cancel_url=f"https://quoteboss.io/q/{quote_id}",
            payment_intent_data={
                'application_fee_amount': application_fee_cents,
                'transfer_data': {
                    'destination': contractor['stripe_account_id'],
                },
            },
        )
        return jsonify({"checkout_url": checkout_session.url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/feedback")
def feedback_page():
    if not session.get('whop_user_id'):
        return redirect('/access')
    return render_template("feedback.html")

@app.route("/api/feedback", methods=["POST"])
@limiter.limit("5 per minute")
def submit_feedback():
    if not session.get('whop_user_id'):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True)
    msg = data.get('message', '').strip()
    if not msg:
        return jsonify({"error": "Message required"}), 400
    category = data.get('category', '')
    save_feedback(
        session['whop_user_id'],
        data.get('rating', 0),
        category,
        msg
    )
    # Alert on urgent or bug submissions
    if category in ('urgent', 'bug'):
        send_feedback_alert(category, msg, session['whop_user_id'])
    return jsonify({"success": True})

OWNER_ID = 'user_rYGUC3pFlNEz5'

def send_feedback_alert(category, message, user_id):
    """Send email alert for urgent/bug feedback."""
    try:
        smtp_user = os.environ.get('ALERT_EMAIL_USER', '')
        smtp_pass = os.environ.get('ALERT_EMAIL_PASS', '')
        alert_to = os.environ.get('ALERT_EMAIL_TO', 'support@quoteboss.io')
        if not smtp_user or not smtp_pass:
            return
        labels = {'urgent': '🚨 URGENT', 'bug': '🐛 Bug'}
        label = labels.get(category, category)
        subject = f"QuoteBoss Feedback: {label}"
        body = f"{label} feedback from {user_id}:\n\n{message}\n\nView all: https://quoteboss.io/admin/feedback"
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = smtp_user
        msg['To'] = alert_to
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
    except Exception:
        pass  # Never crash the app over an email

@app.route("/admin/feedback")
def admin_feedback():
    if session.get('whop_user_id') != OWNER_ID:
        return "Unauthorized", 403
    rows = get_all_feedback()
    stars = {1: "1/5", 2: "2/5", 3: "3/5", 4: "4/5", 5: "5/5", 0: "No rating"}
    category_styles = {
        'urgent': 'border:2px solid #ef4444;background:#fef2f2;',
        'bug': 'border:2px solid #f59e0b;background:#fffbeb;',
        'suggestion': 'border:1px solid #3b82f6;background:#eff6ff;',
        'praise': 'border:1px solid #10b981;background:#ecfdf5;',
    }
    category_labels = {
        'urgent': '🚨 URGENT', 'bug': '🐛 Bug', 'suggestion': '💡 Idea', 'praise': '⭐ Praise',
    }
    html = "<style>body{font-family:sans-serif;padding:2rem;max-width:800px;margin:0 auto} .entry{border-radius:8px;padding:1rem;margin-bottom:1rem;} .meta{font-size:0.8rem;color:#555;margin-bottom:0.5rem;font-weight:600;} .msg{font-size:0.95rem;}</style>"
    urgent_count = sum(1 for r in rows if r.get('category') == 'urgent')
    html += f"<h2>Feedback ({len(rows)} total{f' -- <span style=color:red>{urgent_count} urgent</span>' if urgent_count else ''})</h2>"
    for r in rows:
        cat = r.get('category', 'suggestion')
        style = category_styles.get(cat, 'border:1px solid #ddd;')
        label = category_labels.get(cat, cat)
        html += f"""<div class='entry' style='{style}'>
          <div class='meta'>{label} &nbsp;|&nbsp; {r['created_at'][:16]} &nbsp;|&nbsp; {r['whop_user_id']}</div>
          <div class='msg'>{r['message']}</div>
        </div>"""
    if not rows:
        html += "<p>No feedback yet.</p>"
    return html


@app.route("/faq")
def faq_page():
    if not session.get('whop_user_id'):
        return redirect('/access')
    return render_template("faq.html")


@app.route("/terms")
def terms_page():
    return render_template("terms.html")


@app.route("/privacy")
def privacy_page():
    return render_template("privacy.html")


@app.route("/history")
def quote_history():
    if not session.get('whop_user_id'):
        return redirect('/access')
    from database import get_db, _placeholder
    conn = get_db()
    c = conn.cursor()
    ph = _placeholder()
    c.execute(
        f'SELECT quote_id, quote_data, created_at, accepted, accepted_at FROM quotes WHERE whop_user_id = {ph} ORDER BY created_at DESC LIMIT 50',
        (session['whop_user_id'],)
    )
    rows = c.fetchall()
    conn.close()
    import json as json_lib
    quotes = []
    quote_ids = []
    for row in rows:
        try:
            qd = json_lib.loads(row['quote_data'] if not isinstance(row, dict) else row['quote_data'])
            if not isinstance(row, dict):
                row_dict = dict(row)
            else:
                row_dict = row
            qid = row_dict['quote_id']
            quote_ids.append(qid)
            quotes.append({
                'quote_id': qid,
                'created_at': str(row_dict['created_at'])[:10],
                'trade': qd.get('trade', ''),
                'job_type': qd.get('job_type', ''),
                'total_min': qd.get('total_min', 0),
                'total_max': qd.get('total_max', 0),
                'contractor_business': qd.get('contractor_business', ''),
                'accepted': bool(row_dict.get('accepted', 0)),
                'accepted_at': str(row_dict.get('accepted_at', '') or ''),
                'payment_terms': qd.get('payment_terms', 'full'),
                'payment_terms_label': qd.get('payment_terms_label', ''),
                'deposit_pct': qd.get('deposit_pct', 100),
                'final_price': qd.get('final_price', qd.get('total_max', 0)),
            })
        except Exception:
            pass

    view_counts = get_quote_views_batch(quote_ids) if quote_ids else {}
    return render_template("history.html", quotes=quotes, view_counts=view_counts)


@app.route("/tutorials")
def tutorials_page():
    if not session.get('whop_user_id'):
        return redirect('/access')
    tutorials = [
        {"title": "Getting Started with QuoteBoss", "description": "Sign in, set up your profile, and send your first quote in under 5 minutes.", "video_url": ""},
        {"title": "Roofing Quotes", "description": "How to quote full replacements, repairs, and gutters accurately.", "video_url": ""},
        {"title": "HVAC Quotes", "description": "Adding equipment costs, labor, and permits to HVAC quotes.", "video_url": ""},
        {"title": "Plumbing Quotes", "description": "Handling parts, labor, and markup for plumbing jobs.", "video_url": ""},
        {"title": "Electrical Quotes", "description": "Panel upgrades, rewiring, and fixture installs with custom line items.", "video_url": ""},
        {"title": "Pressure Washing Quotes", "description": "Quoting house washes, driveways, and commercial jobs by square foot.", "video_url": ""},
        {"title": "Collecting Payments", "description": "Connect Stripe and get paid directly from your quote links.", "video_url": ""},
    ]
    return render_template("tutorials.html", tutorials=tutorials)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
