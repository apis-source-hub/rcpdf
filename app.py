import io
import os
import base64
import time
from datetime import datetime
import requests
from flask import Flask, request, jsonify
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.barcode import qr

app = Flask(__name__)

# Real Browser Headers to bypass Cloudflare Worker blocking
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


def normalize_rc_data(raw_data: dict) -> dict:
    """Extract and normalize fields from nested or flat API responses."""
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
    v_class = d.get("vehicleClass") or d.get("Vehicle_Class_Core") or d.get("Vehicle_Class") or "M-CYCLE/SCOOTER"
    maker = d.get("manufacturer") or d.get("Make_Name") or d.get("Vahan_Make") or ""
    model = d.get("vehicle") or d.get("Model_Name") or d.get("Vahan_Model") or ""
    color = d.get("color") or d.get("Color") or "WHITE"
    seat = str(d.get("seatCapacity") or d.get("Seating_Capacity") or d.get("Vahan_Seating_Capacity") or "2")
    unladen = str(d.get("unladenWeight") or d.get("Vahan_GVW") or "150")
    cc = str(d.get("cubicCapacity") or d.get("Cubic_Capacity") or d.get("Vahan_Cubic_Capacity") or "0")

    m_month = str(d.get("Manufacture_Month") or "")
    m_year = str(d.get("Manufacture_Year") or d.get("Year") or "")
    mfg_my = f"{m_month}/{m_year}".strip("/") if (m_month or m_year) else d.get("manufacturerMonthYear", "")

    rto_name = d.get("RTO_Name") or d.get("CityofRegitration") or d.get("citycamal") or ""
    rto_data = d.get("rtoData", {})
    state_name = rto_data.get("statename", "") if isinstance(rto_data, dict) else ""
    if not state_name and rto_name:
        state_name = rto_name

    expiry = d.get("insuranceUpto") or d.get("Pyp_Policy_Expiry_Date") or ""

    # Clean default 'NA' values
    owner_clean = "" if str(owner).upper() in ["NA", "NULL", "NONE"] else str(owner).strip()
    father_clean = "" if str(father).upper() in ["NA", "NULL", "NONE"] else str(father).strip()

    return {
        "regNo": str(reg_no).strip().upper(),
        "regDate": str(reg_date).strip(),
        "insuranceUpto": str(expiry).strip(),
        "chassis": str(chassis).replace("~", " ").strip(),
        "engine": str(engine).strip(),
        "owner": owner_clean,
        "ownerFatherName": father_clean,
        "address": str(address).strip(),
        "fuelType": str(fuel).strip().upper(),
        "vehicleClass": v_cat_format(v_class),
        "maker": str(maker).strip().upper(),
        "model": str(model).strip().upper(),
        "color": str(color).strip().upper(),
        "seatCapacity": seat.strip(),
        "unladenWeight": unladen.strip(),
        "cubicCapacity": cc.strip(),
        "mfgMonthYear": mfg_my.strip(),
        "stateName": state_name.strip() if state_name else "India",
        "regAuthority": str(rto_name).strip(),
    }


def v_cat_format(val: str) -> str:
    val_upper = str(val).upper()
    if "2WN" in val_upper or "SCOOTER" in val_upper or "CYCLE" in val_upper:
        return "TWO WHEELER(NT)"
    return val_upper


def fetch_rc_data(vehicle_no: str) -> dict:
    errors = []

    # --- ATTEMPT 1: Secondary API (Direct vehiclev2) ---
    api_2_url = "https://vehiclev2.vk177384.workers.dev/"
    try:
        resp2 = requests.get(
            api_2_url,
            params={"number": vehicle_no, "api_key": "sneha"},
            headers=HEADERS,
            timeout=10
        )
        if resp2.status_code == 200:
            data2 = resp2.json()
            if data2.get("status") == "Success" or "data" in data2 or "registration_number" in data2:
                return normalize_rc_data(data2)
            elif data2.get("statusCode") == 200 and "response" in data2:
                return normalize_rc_data(data2["response"])
        else:
            errors.append(f"vehiclev2 returned HTTP {resp2.status_code}")
    except Exception as e:
        errors.append(f"vehiclev2 failed: {e}")

    # --- ATTEMPT 2: Primary Fallback API ---
    api_1_url = "https://vahanapi.vk177384.workers.dev/"
    try:
        resp1 = requests.get(
            api_1_url,
            params={"vehicle_no": vehicle_no},
            headers=HEADERS,
            timeout=10
        )
        if resp1.status_code == 200:
            data1 = resp1.json()
            if data1.get("statusCode") == 200 and "response" in data1:
                return normalize_rc_data(data1["response"])
        else:
            errors.append(f"vahanapi returned HTTP {resp1.status_code}")
    except Exception as e:
        errors.append(f"vahanapi failed: {e}")

    error_detail = " | ".join(errors) if errors else "No vehicle record found"
    raise ValueError(f"Vehicle fetch failed for {vehicle_no!r}: {error_detail}")


def format_date_to_card(date_str: str) -> str:
    if not date_str:
        return ""
    date_str = date_str.replace("-", "/")
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


def card_issue_date(regn_dt: str) -> str:
    if not regn_dt:
        return ""
    regn_dt = regn_dt.replace("-", "/")
    parts = regn_dt.split("/")
    if len(parts) == 3:
        return f"{parts[1].zfill(2)}-{parts[2]}"
    return regn_dt


def generate_rc_pdf_bytes(d: dict) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(842, 595))

    regn_no = d.get("regNo", "")
    regn_dt = format_date_to_card(d.get("regDate", ""))
    validity = format_date_to_card(d.get("insuranceUpto", ""))
    chassis = d.get("chassis", "")
    engine_no = d.get("engine", "")
    owner_name = d.get("owner", "")
    father_name = d.get("ownerFatherName", "")
    address = d.get("address", "")
    fuel = d.get("fuelType", "PETROL")
    veh_cat = d.get("vehicleClass", "TWO WHEELER(NT)")
    maker = d.get("maker", "")
    model = d.get("model", "")
    color = d.get("color", "WHITE")
    seat_cap = d.get("seatCapacity", "2")
    unld_wt = d.get("unladenWeight", "150")
    cubic_cap = d.get("cubicCapacity", "0")
    mfg_my = d.get("mfgMonthYear", "")
    state_name = d.get("stateName", "India")
    reg_authority = d.get("regAuthority", "")
    issue_date = card_issue_date(d.get("regDate", ""))

    card_w, card_h = 360, 225
    y_pos = 185

    # ---------------- FRONT CARD ----------------
    x1 = 45
    c.setStrokeColor(colors.HexColor("#222222"))
    c.setLineWidth(1)
    c.setFillColor(colors.HexColor("#eef7fc"))
    c.roundRect(x1, y_pos, card_w, card_h, 8, fill=1, stroke=1)

    # Header
    c.setFillColor(colors.HexColor("#002855"))
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(x1 + 180, y_pos + card_h - 20, "Indian Union Vehicle Registration Certificate")
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(x1 + 180, y_pos + card_h - 34, f"Issued by Government of {state_name}")

    # Badges
    c.setFillColor(colors.HexColor("#00a8e8"))
    c.circle(x1 + card_w - 38, y_pos + card_h - 25, 9, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#f39c12"))
    c.circle(x1 + card_w - 16, y_pos + card_h - 25, 9, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(x1 + card_w - 38, y_pos + card_h - 28, "NT")
    c.drawCentredString(x1 + card_w - 16, y_pos + card_h - 28, regn_no[:2] if len(regn_no) >= 2 else "IND")

    # Front Details Grid
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(x1 + 15, y_pos + 165, "Regn. No")
    c.drawString(x1 + 105, y_pos + 165, "Date of Regn.")
    c.drawString(x1 + 195, y_pos + 165, "Regn. Validity")
    c.drawString(x1 + 295, y_pos + 165, "Owner Serial")

    c.setFont("Helvetica", 7.5)
    c.drawString(x1 + 15, y_pos + 153, regn_no)
    c.drawString(x1 + 105, y_pos + 153, regn_dt)
    c.drawString(x1 + 195, y_pos + 153, validity)
    c.drawString(x1 + 310, y_pos + 153, "1")

    # Chassis & Engine
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(x1 + 15, y_pos + 138, "Chassis Number:")
    c.setFont("Helvetica", 7.5)
    c.drawString(x1 + 115, y_pos + 138, chassis)

    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(x1 + 15, y_pos + 123, "Engine Number:")
    c.setFont("Helvetica", 7.5)
    c.drawString(x1 + 115, y_pos + 123, engine_no)

    # Owner & Father Name
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(x1 + 15, y_pos + 108, "Owner Name:")
    c.setFont("Helvetica", 7.5)
    c.drawString(x1 + 115, y_pos + 108, owner_name)

    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(x1 + 15, y_pos + 93, "Father/Husband:")
    c.setFont("Helvetica", 7.5)
    c.drawString(x1 + 115, y_pos + 93, father_name)

    # Address
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(x1 + 15, y_pos + 78, "Address:")
    c.setFont("Helvetica", 7)
    addr_line1 = address[:45]
    addr_line2 = address[45:90]
    c.drawString(x1 + 115, y_pos + 78, addr_line1)
    if addr_line2:
        c.drawString(x1 + 115, y_pos + 68, addr_line2)

    # Fuel & Norms
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(x1 + 15, y_pos + 50, "Fuel:")
    c.setFont("Helvetica", 7.5)
    c.drawString(x1 + 50, y_pos + 50, fuel)

    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(x1 + 150, y_pos + 50, "Emission Norms:")
    c.setFont("Helvetica", 7.5)
    c.drawString(x1 + 235, y_pos + 50, "BHARAT STAGE IV")

    # ---------------- BACK CARD ----------------
    x2 = 435
    c.setFillColor(colors.HexColor("#eef7fc"))
    c.roundRect(x2, y_pos, card_w, card_h, 8, fill=1, stroke=1)

    # Header
    c.setFillColor(colors.HexColor("#002855"))
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(x2 + 55, y_pos + card_h - 22, f"VEHICLE CLASS : {veh_cat}")

    # QR Code
    qr_code = qr.QrCodeWidget(f"RC:{regn_no}|CH:{chassis}|ENG:{engine_no}")
    qr_code.barWidth = 65
    qr_code.barHeight = 65
    d_obj = Drawing(65, 65)
    d_obj.add(qr_code)
    d_obj.drawOn(c, x2 + 15, y_pos + 95)

    # Back Specs
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(x2 + 15, y_pos + 185, "Regn. Number:")
    c.setFont("Helvetica", 7.5)
    c.drawString(x2 + 15, y_pos + 172, regn_no)

    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(x2 + 100, y_pos + 165, "Maker:")
    c.setFont("Helvetica", 7.5)
    c.drawString(x2 + 150, y_pos + 165, maker[:30])

    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(x2 + 100, y_pos + 150, "Model:")
    c.setFont("Helvetica", 7.5)
    c.drawString(x2 + 150, y_pos + 150, model[:30])

    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(x2 + 100, y_pos + 135, "Color / Body:")
    c.setFont("Helvetica", 7.5)
    c.drawString(x2 + 170, y_pos + 135, f"{color} / SALOON")

    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(x2 + 100, y_pos + 120, "Seating Cap:")
    c.setFont("Helvetica", 7.5)
    c.drawString(x2 + 170, y_pos + 120, seat_cap)

    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(x2 + 100, y_pos + 105, "Unladen Wt:")
    c.setFont("Helvetica", 7.5)
    c.drawString(x2 + 170, y_pos + 105, f"{unld_wt} Kg")

    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(x2 + 15, y_pos + 65, f"Mfg Month-Year: {mfg_my}")
    c.drawString(x2 + 170, y_pos + 65, f"Cubic Cap: {cubic_cap}")
    c.drawString(x2 + 15, y_pos + 45, f"Reg Authority: {reg_authority}")
    c.drawString(x2 + 15, y_pos + 25, f"Card Issue Date: {issue_date}")

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()


@app.route("/rc")
def rc_pdf():
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
        pdf_bytes = generate_rc_pdf_bytes(data)
        pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")

        return jsonify({
            "status": "success",
            "message": "RC PDF fetched successfully",
            "timestamp": current_timestamp,
            "rcno": vehicle,
            "pdf": pdf_base64,
            "execution_time": f"{round(time.time() - start_time, 3)}s"
        }), 200

    except Exception as exc:
        return jsonify({
            "status": "error",
            "message": str(exc),
            "timestamp": current_timestamp,
            "rcno": vehicle,
            "pdf": None,
            "execution_time": f"{round(time.time() - start_time, 3)}s"
        }), 500


@app.route("/")
def index():
    return jsonify({
        "status": "online",
        "endpoint": "/rc?vehicle=AP07CW1616"
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
