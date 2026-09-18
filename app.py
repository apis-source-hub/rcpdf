import io
import os
import re
import random
import base64
import requests
from flask import Flask, request, jsonify, Response, send_file
from PIL import Image

app = Flask(__name__)

# Image API Configurations
IMG_API_URL = "https://www.allimagetools.com/api/html-to-image"
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template.html")


def fetch_rc_data(vehicle_no: str) -> dict:
    # --- ATTEMPT 1: Primary API ---
    api_1_url = "https://vahanapi.vk177384.workers.dev/"
    try:
        resp1 = requests.get(api_1_url, params={"vehicle_no": vehicle_no}, timeout=30)
        if resp1.status_code == 200:
            data1 = resp1.json()
            if data1.get("statusCode") == 200 and "response" in data1:
                return data1["response"]
    except Exception:
        pass # Agar API 1 fail hui toh aage API 2 par jayega

    # --- ATTEMPT 2: Secondary API (Fallback) ---
    api_2_url = "https://vehiclev2.vk177384.workers.dev/"
    try:
        resp2 = requests.get(api_2_url, params={"number": vehicle_no, "api_key": "sneha"}, timeout=30)
        if resp2.status_code == 200:
            data2 = resp2.json()
            # Agar structure pehli API jaisa hai
            if data2.get("statusCode") == 200 and "response" in data2:
                return data2["response"]
            # Agar secondary API direct data return karti hai
            elif "regNo" in data2 or "chassis" in data2:
                return data2
    except Exception:
        pass # Agar dono fail ho gaye

    # Agar dono API se koi data nahi mila
    raise ValueError(f"No data found or both APIs failed for vehicle {vehicle_no!r}")


def mfg_month_year(raw: str) -> str:
    if not raw:
        return ""
    return raw


def extract_state(rto_data: dict) -> str:
    if not rto_data:
        return "India"
    return rto_data.get("statename", "India").strip()


def card_issue_date(regn_dt: str) -> str:
    """Convert DD/MM/YYYY or D/M/YYYY to MM-YYYY"""
    if not regn_dt:
        return ""
    parts = regn_dt.split("/")
    if len(parts) == 3:
        month = parts[1].zfill(2)
        return f"{month}-{parts[2]}"
    return regn_dt


def format_date_to_card(date_str: str) -> str:
    """Converts D/M/YYYY to DD-MMM-YYYY format matching template placeholders"""
    if not date_str:
        return ""
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    parts = date_str.split("/")
    if len(parts) == 3:
        try:
            day = parts[0].zfill(2)
            month_idx = int(parts[1]) - 1
            year = parts[2]
            if 0 <= month_idx < 12:
                return f"{day}-{months[month_idx]}-{year}"
        except Exception:
            pass
    return date_str


def split_address(address_str: str, max_chars: int = 35) -> tuple:
    """Splits address into two lines seamlessly without breaking words"""
    if len(address_str) <= max_chars:
        return address_str, ""

    break_idx = address_str.rfind(" ", 0, max_chars)
    if break_idx == -1:
        break_idx = max_chars

    line1 = address_str[:break_idx].strip()
    line2 = address_str[break_idx:].strip()

    if len(line2) > 45:
        line2 = line2[:42] + "..."

    return line1, line2


def build_html(data: dict) -> str:
    with open(TEMPLATE, "r", encoding="utf-8") as f:
        html = f.read()

    rto_data      = data.get("rtoData", {})
    regn_no       = data.get("regNo", "").strip()

    raw_reg_date  = data.get("regDate", "").strip()
    regn_dt       = format_date_to_card(raw_reg_date)

    raw_expiry    = data.get("insuranceUpto", "").strip()
    validity      = format_date_to_card(raw_expiry)

    chassis       = data.get("chassis", "").replace("~", " ").strip()
    engine_no     = data.get("engine", "").strip()
    owner_name    = data.get("owner", "").strip()
    father_name   = data.get("ownerFatherName", "").strip()
    if father_name.upper() == "NA" or not father_name:
        father_name = ""

    present_addr  = data.get("presentAddress", "").strip()
    perm_addr     = data.get("permAddress", "").strip()
    full_address  = present_addr if len(present_addr) >= len(perm_addr) else perm_addr

    addr_line1, addr_line2 = split_address(full_address, max_chars=35)

    fuel          = data.get("fuelType", "").strip().upper()
    norms         = "BHARAT STAGE IV"
    veh_cat       = data.get("vehicleClass", "").strip()
    maker         = data.get("manufacturer", "").strip()
    model         = data.get("vehicle", "").strip()
    color         = "WHITE"
    body_type     = "SALOON"

    seat_cap      = str(data.get("seatCapacity", "5")).strip()
    unld_wt       = str(data.get("unladenWeight", "1500")).strip()
    cubic_cap     = str(data.get("cubicCapacity", "")).strip()
    no_cyl        = "4"

    mfg_my        = mfg_month_year(data.get("manufacturerMonthYear", ""))
    reg_authority = data.get("regAuthority", "").strip()
    issue_date    = card_issue_date(raw_reg_date)
    state_name    = extract_state(rto_data)

    html = html.replace(">Government of Rajasthan<",   f">Government of {state_name}<")
    html = html.replace(">RJ06SQ4302<",                f">{regn_no}<")
    html = html.replace(">27-Apr-2011<",               f">{regn_dt}<")
    html = html.replace(">26-Apr-2026<",               f">{validity}<")
    html = html.replace(">MD626AG45B1C19003<",         f">{chassis}<")
    html = html.replace(">064CB1121025<",              f">{engine_no}<")
    html = html.replace(">SH HAMID KHAN<",             f">{owner_name}<")
    html = html.replace(">UMAID KHA KAYAMKHANI<",      f">{father_name}<")

    html = re.sub(
        r'(ff1 fs2 fc0 sc0 ls0 ws0">), 311001(<)',
        lambda m: m.group(1) + addr_line1 + m.group(2),
        html
    )

    if addr_line2:
        pattern = r'(_address_line_placeholder_match_)?(ff1 fs2 fc0 sc0 ls0 ws0">' + re.escape(addr_line1) + r'</div>\s*<div class="[^"]*ff1 fs2 fc0 sc0 ls0 ws0">)</div>'
        html = re.sub(
            pattern,
            r'\2' + addr_line2 + r'</div>',
            html,
            count=1
        )

    html = html.replace(">PETROL<",                    f">{fuel}<")
    html = html.replace(">BHARAT STAGE II<",           f">{norms}<")
    html = html.replace(">VEHICLE CLASS : TWO WHEELER(NT)<",
                        f">VEHICLE CLASS : {veh_cat}<")
    html = html.replace(">TVS MOTOR COMPANY LTD<",     f">{maker}<")
    html = html.replace(">TVS WEGO<",                  f">{model}<")
    html = html.replace(">BROWN<",                     f">{color}<")
    html = html.replace(">SOLO<",                      f">{body_type}<")
    html = html.replace(">110.00<",                    f">{cubic_cap}<")
    html = html.replace(">No of Cylinders : 1<",       f">No of Cylinders : {no_cyl}<")
    html = html.replace(">4/2011<",                    f">{mfg_my}<")
    html = html.replace(">BHILWARA DTO, Rajasthan<",   f">{reg_authority}<")
    html = html.replace(">Card Issue Date (04-2011)<",
                        f">Card Issue Date ({issue_date})<")

    html = re.sub(
        r'(Seating in all Capacity</div>.*?ff1.*?>)2(<)',
        lambda m: m.group(1) + seat_cap + m.group(2),
        html, flags=re.DOTALL
    )
    html = re.sub(
        r'(Unladen Weight Kg</div>.*?ff1.*?>)110(<)',
        lambda m: m.group(1) + unld_wt + m.group(2),
        html, flags=re.DOTALL
    )
    return html


def random_headers() -> dict:
    ua_templates = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v}.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v}.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v}.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Linux; Android {a}; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v}.0.0.0 Mobile Safari/537.36",
    ]
    chrome_ver = random.randint(120, 137)
    android_ver = random.randint(10, 15)
    ua = random.choice(ua_templates).format(v=chrome_ver, a=android_ver)
    return {
        "accept": "*/*",
        "content-type": "application/json",
        "origin": "https://www.allimagetools.com",
        "referer": "https://www.allimagetools.com/html-to-image",
        "user-agent": ua,
    }


def html_to_image(html: str) -> bytes:
    payload = {
        "html": html,
        "width": 894,
        "height": 1264,
        "isMobile": False,
        "fullPage": True,
        "format": "png",
        "quality": 90,
        "scale": 3,
        "darkMode": False,
        "delay": 0,
        "customCss": "",
        "hideElements": "",
    }
    headers = random_headers()
    resp = requests.post(IMG_API_URL, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    b64 = resp.json().get("image")
    if not b64:
        raise ValueError("AllImageTools API did not return a base64 image")
    b64_clean = re.sub(r"^data:image/\w+;base64,", "", b64)
    return base64.b64decode(b64_clean)


def image_to_pdf(img_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    pdf_buf = io.BytesIO()
    img.save(pdf_buf, "PDF")
    return pdf_buf.getvalue()


@app.route("/rc")
def rc_pdf():
    vehicle = request.args.get("vehicle", "").strip().upper()
    if not vehicle:
        return jsonify({"error": "vehicle parameter required"}), 400

    try:
        data = fetch_rc_data(vehicle)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    try:
        html = build_html(data)
    except Exception as exc:
        return jsonify({"error": f"Template error: {exc}"}), 500

    try:
        img_bytes = html_to_image(html)
    except Exception as exc:
        return jsonify({"error": f"Image generation failed: {exc}"}), 500

    try:
        pdf_bytes = image_to_pdf(img_bytes)
    except Exception as exc:
        return jsonify({"error": f"PDF conversion failed: {exc}"}), 500

    pdf_io = io.BytesIO(pdf_bytes)
    pdf_io.seek(0)
    return send_file(
        pdf_io, 
        mimetype="application/pdf", 
        as_attachment=True, 
        download_name=f"RC_{vehicle}.pdf"
    )


@app.route("/rcimg")
def rc_image():
    vehicle = request.args.get("vehicle", "").strip().upper()
    if not vehicle:
        return jsonify({"error": "vehicle parameter required"}), 400

    try:
        data = fetch_rc_data(vehicle)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    try:
        html = build_html(data)
    except Exception as exc:
        return jsonify({"error": f"Template error: {exc}"}), 500

    try:
        img_bytes = html_to_image(html)
    except Exception as exc:
        return jsonify({"error": f"Image generation failed: {exc}"}), 500

    img_io = io.BytesIO(img_bytes)
    img_io.seek(0)
    return send_file(
        img_io, 
        mimetype="image/png", 
        as_attachment=True, 
        download_name=f"RC_{vehicle}.png"
    )


@app.route("/rchtml")
def rc_html():
    vehicle = request.args.get("vehicle", "").strip().upper()
    if not vehicle:
        return jsonify({"error": "vehicle parameter required"}), 400

    try:
        data = fetch_rc_data(vehicle)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    try:
        html = build_html(data)
    except Exception as exc:
        return jsonify({"error": f"Template error: {exc}"}), 500

    return Response(html, mimetype="text/html")


@app.route("/")
def index():
    return (
        "<h2>RC Card PDF Generator</h2>"
        "<p>Available Routes:</p>"
        "<ul>"
        "<li><code>/rc?vehicle=HR26EV0001</code> — Direct PDF Download</li>"
        "<li><code>/rcimg?vehicle=HR26EV0001</code> — Direct Image Download</li>"
        "<li><code>/rchtml?vehicle=HR26EV0001</code> — Returns raw HTML</li>"
        "</ul>"
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
