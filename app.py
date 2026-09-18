import io
import os
import re
import random
import base64
import time
from datetime import datetime
import requests
from flask import Flask, request, jsonify, Response, send_file
from PIL import Image

app = Flask(__name__)

IMG_API_URL = "https://www.allimagetools.com/api/html-to-image"
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template.html")

session = requests.Session()


def normalize_api_data(raw_data: dict) -> dict:
    """Handles both primary API format and secondary API format."""
    d = raw_data.get("data", raw_data) if isinstance(raw_data, dict) else {}

    reg_no = d.get("regNo") or d.get("Registration_Number") or d.get("registration_number") or ""
    reg_date = d.get("regDate") or d.get("Registration_Date") or d.get("RegistrationDate") or ""
    chassis = d.get("chassis") or d.get("Chassis_Number") or ""
    engine = d.get("engine") or d.get("Engin_Number") or d.get("Engine_Number") or ""
    owner = d.get("owner") or d.get("Owner_Name") or ""
    father = d.get("ownerFatherName") or d.get("Father_Name") or ""

    address = (
        d.get("presentAddress")
        or d.get("Permanent_Address")
        or d.get("Communication_Address")
        or d.get("permAddress")
        or ""
    )

    fuel = d.get("fuelType") or d.get("Fuel_Type") or d.get("Fuel_Name") or "PETROL"
    v_class = d.get("vehicleClass") or d.get("Vehicle_Class_Core") or d.get("Vehicle_Class") or "TWO WHEELER(NT)"
    maker = d.get("manufacturer") or d.get("Make_Name") or d.get("Vahan_Make") or ""
    model = d.get("vehicle") or d.get("Model_Name") or d.get("Vahan_Model") or ""
    color = d.get("color") or d.get("Color") or "WHITE"
    seat = str(d.get("seatCapacity") or d.get("Seating_Capacity") or d.get("Vahan_Seating_Capacity") or "2")
    unladen = str(d.get("unladenWeight") or d.get("Vahan_GVW") or "110")
    cc = str(d.get("cubicCapacity") or d.get("Cubic_Capacity") or d.get("Vahan_Cubic_Capacity") or "110.00")

    m_month = str(d.get("Manufacture_Month") or "")
    m_year = str(d.get("Manufacture_Year") or d.get("Year") or "")
    mfg_my = f"{m_month}/{m_year}".strip("/") if (m_month or m_year) else d.get("manufacturerMonthYear", "")

    rto_name = d.get("RTO_Name") or d.get("CityofRegitration") or d.get("citycamal") or ""
    rto_data = d.get("rtoData", {})
    state_name = rto_data.get("statename", "") if isinstance(rto_data, dict) else ""
    if not state_name and rto_name:
        state_name = rto_name

    expiry = d.get("insuranceUpto") or d.get("Pyp_Policy_Expiry_Date") or ""

    owner_clean = "" if str(owner).upper() in ["NA", "NULL", "NONE"] else str(owner).strip()
    father_clean = "" if str(father).upper() in ["NA", "NULL", "NONE"] else str(father).strip()

    return {
        "regNo": str(reg_no).strip().upper(),
        "regDate": str(reg_date).strip().replace("-", "/"),
        "insuranceUpto": str(expiry).strip().replace("-", "/"),
        "chassis": str(chassis).replace("~", " ").strip(),
        "engine": str(engine).strip(),
        "owner": owner_clean,
        "ownerFatherName": father_clean,
        "presentAddress": str(address).strip(),
        "permAddress": str(address).strip(),
        "fuelType": str(fuel).strip().upper(),
        "vehicleClass": str(v_class).strip(),
        "manufacturer": str(maker).strip().upper(),
        "vehicle": str(model).strip().upper(),
        "color": str(color).strip().upper(),
        "seatCapacity": seat.strip(),
        "unladenWeight": unladen.strip(),
        "cubicCapacity": cc.strip(),
        "manufacturerMonthYear": mfg_my.strip(),
        "rtoData": {"statename": state_name.strip() if state_name else "India"},
        "regAuthority": str(rto_name).strip()
    }


def fetch_rc_data(vehicle_no: str) -> dict:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*"
    }

    # --- ATTEMPT 1: Secondary Worker API ---
    api_2_url = "https://vehiclev2.vk177384.workers.dev/"
    try:
        resp2 = session.get(api_2_url, params={"number": vehicle_no, "api_key": "sneha"}, headers=headers, timeout=12)
        if resp2.status_code == 200:
            data2 = resp2.json()
            if data2.get("status") == "Success" or "data" in data2 or "registration_number" in data2:
                return normalize_api_data(data2)
            elif data2.get("statusCode") == 200 and "response" in data2:
                return normalize_api_data(data2["response"])
    except Exception:
        pass

    # --- ATTEMPT 2: Primary Worker API ---
    api_1_url = "https://vahanapi.vk177384.workers.dev/"
    try:
        resp1 = session.get(api_1_url, params={"vehicle_no": vehicle_no}, headers=headers, timeout=12)
        if resp1.status_code == 200:
            data1 = resp1.json()
            if data1.get("statusCode") == 200 and "response" in data1:
                return normalize_api_data(data1["response"])
    except Exception:
        pass

    raise ValueError(f"No data found or both APIs failed for vehicle {vehicle_no!r}")


def mfg_month_year(raw: str) -> str:
    return raw if raw else ""


def extract_state(rto_data: dict) -> str:
    if not rto_data:
        return "India"
    return rto_data.get("statename", "India").strip()


def card_issue_date(regn_dt: str) -> str:
    if not regn_dt:
        return ""
    parts = regn_dt.split("/")
    if len(parts) == 3:
        month = parts[1].zfill(2)
        return f"{month}-{parts[2]}"
    return regn_dt


def format_date_to_card(date_str: str) -> str:
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
    color         = data.get("color", "WHITE").strip()
    body_type     = "SALOON"

    seat_cap      = str(data.get("seatCapacity", "2")).strip()
    unld_wt       = str(data.get("unladenWeight", "110")).strip()
    cubic_cap     = str(data.get("cubicCapacity", "")).strip()
    no_cyl        = "1"

    mfg_my        = mfg_month_year(data.get("manufacturerMonthYear", ""))
    reg_authority = data.get("regAuthority", "").strip()
    issue_date    = card_issue_date(raw_reg_date)
    state_name    = extract_state(rto_data)

    state_prefix = regn_no[:2] if len(regn_no) >= 2 else "RJ"

    html = html.replace(">Government of Rajasthan<",   f">Government of {state_name}<")
    html = html.replace(">RJ06SQ4302<",                f">{regn_no}<")
    html = html.replace(">27-Apr-2011<",               f">{regn_dt}<")
    html = html.replace(">26-Apr-2026<",               f">{validity}<")
    html = html.replace(">MD626AG45B1C19003<",         f">{chassis}<")
    html = html.replace(">064CB1121025<",              f">{engine_no}<")
    html = html.replace(">SH HAMID KHAN<",             f">{owner_name}<")
    html = html.replace(">UMAID KHA KAYAMKHANI<",      f">{father_name}<")

    # Front & Back state badge circles
    html = re.sub(r'(>RJ<)', f">{state_prefix}<", html)

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
        "quality": 85,
        "scale": 2,
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
    img.save(pdf_buf, "PDF", resolution=150.0)
    return pdf_buf.getvalue()


# --- 1. JSON RESPONSE WITH BASE64 PDF ---
@app.route("/rc")
def rc_json():
    start_time = time.time()
    current_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    vehicle = request.args.get("vehicle", "").strip().upper()
    if not vehicle:
        return jsonify({
            "status": "error",
            "message": "vehicle parameter required",
            "timestamp": current_timestamp,
            "rcno": vehicle,
            "pdf": None,
            "execution_time": f"{round(time.time() - start_time, 3)}s"
        }), 400

    try:
        data = fetch_rc_data(vehicle)
        html = build_html(data)
        img_bytes = html_to_image(html)
        pdf_bytes = image_to_pdf(img_bytes)

        pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
        execution_time = f"{round(time.time() - start_time, 3)}s"

        return jsonify({
            "execution_time": execution_time,
            "message": "RC PDF fetched successfully",
            "pdf": pdf_base64,
            "rcno": vehicle,
            "status": "success",
            "timestamp": current_timestamp
        }), 200

    except Exception as exc:
        execution_time = f"{round(time.time() - start_time, 3)}s"
        return jsonify({
            "execution_time": execution_time,
            "message": str(exc),
            "pdf": None,
            "rcno": vehicle,
            "status": "error",
            "timestamp": current_timestamp
        }), 500


# --- 2. DIRECT PDF DOWNLOAD ---
@app.route("/rcdownload")
def rc_pdf_download():
    vehicle = request.args.get("vehicle", "").strip().upper()
    if not vehicle:
        return jsonify({"error": "vehicle parameter required"}), 400

    try:
        data = fetch_rc_data(vehicle)
        html = build_html(data)
        img_bytes = html_to_image(html)
        pdf_bytes = image_to_pdf(img_bytes)

        pdf_io = io.BytesIO(pdf_bytes)
        pdf_io.seek(0)
        return send_file(
            pdf_io,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"RC_{vehicle}.pdf"
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# --- 3. DIRECT IMAGE DOWNLOAD ---
@app.route("/rcimg")
def rc_image():
    vehicle = request.args.get("vehicle", "").strip().upper()
    if not vehicle:
        return jsonify({"error": "vehicle parameter required"}), 400

    try:
        data = fetch_rc_data(vehicle)
        html = build_html(data)
        img_bytes = html_to_image(html)

        img_io = io.BytesIO(img_bytes)
        img_io.seek(0)
        return send_file(
            img_io,
            mimetype="image/png",
            as_attachment=True,
            download_name=f"RC_{vehicle}.png"
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# --- 4. RAW HTML ---
@app.route("/rchtml")
def rc_html():
    vehicle = request.args.get("vehicle", "").strip().upper()
    if not vehicle:
        return jsonify({"error": "vehicle parameter required"}), 400

    try:
        data = fetch_rc_data(vehicle)
        html = build_html(data)
        return Response(html, mimetype="text/html")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/")
def index():
    return (
        "<h2>RC Card Generator</h2>"
        "<ul>"
        "<li><code>/rc?vehicle=MH01AB1234</code> — JSON with Base64 PDF</li>"
        "<li><code>/rcdownload?vehicle=MH01AB1234</code> — Direct PDF Download</li>"
        "<li><code>/rcimg?vehicle=MH01AB1234</code> — Direct Image Download</li>"
        "<li><code>/rchtml?vehicle=MH01AB1234</code> — Raw HTML</li>"
        "</ul>"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
