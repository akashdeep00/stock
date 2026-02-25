"""
JioMart Stock Notifier – Scrapfly + JS Scenario Edition
Uses Scrapfly's js_scenario to actually type the pincode into the page,
triggering JioMart's availability check just like a real user would.
"""

import os
import smtplib
import re
import json
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from zoneinfo import ZoneInfo

# ─── CONFIG ──────────────────────────────────────────────────────────────────
PINCODE      = "844505"
PRODUCT_NAME = "Bikaji Bikaner Chowpati Bhelpuri 110g"
PRODUCT_URL  = "https://www.jiomart.com/p/groceries/bikaji-bikaner-chowpati-bhelpuri-110-g/608498429"

GMAIL_SENDER     = os.environ["GMAIL_SENDER"]
GMAIL_PASSWORD   = os.environ["GMAIL_PASSWORD"]
NOTIFY_EMAIL     = os.environ["NOTIFY_EMAIL"]
SCRAPFLY_API_KEY = os.environ["SCRAPFLY_API_KEY"]
# ─────────────────────────────────────────────────────────────────────────────


def check_stock() -> dict:

    # Scrapfly js_scenario: interact with the page to enter pincode
    # then wait for JioMart to update availability
    js_scenario = json.dumps([
        {"wait": 3000},
        # Try to click the pincode input or "Deliver to" section
        {"click": {"selector": "input[placeholder*='PIN' i], input[placeholder*='pincode' i], [class*='pincode'] input", "ignore_if_not_exists": True}},
        {"wait": 500},
        {"fill": {"selector": "input[placeholder*='PIN' i], input[placeholder*='pincode' i], [class*='pincode'] input", "value": PINCODE, "ignore_if_not_exists": True}},
        {"press": {"selector": "input[placeholder*='PIN' i], input[placeholder*='pincode' i], [class*='pincode'] input", "key": "Enter", "ignore_if_not_exists": True}},
        # Wait for availability to update
        {"wait": 5000},
    ])

    params = {
        "key":         SCRAPFLY_API_KEY,
        "url":         PRODUCT_URL,
        "asp":         "true",
        "render_js":   "true",
        "country":     "in",
        "js_scenario": js_scenario,
    }

    print(f"[SCRAPFLY] Fetching page with pincode interaction...")
    try:
        resp = requests.get("https://api.scrapfly.io/scrape", params=params, timeout=120)
        print(f"[SCRAPFLY] HTTP: {resp.status_code}")

        if resp.status_code != 200:
            return {"in_stock": False, "price": "N/A", "error": f"HTTP {resp.status_code}: {resp.text[:300]}"}

        data = resp.json()
        html = data.get("result", {}).get("content", "")
        print(f"[SCRAPFLY] Page size: {len(html)} bytes")

        # Show screenshot URL if available (great for debugging)
        screenshot = data.get("result", {}).get("screenshot_url", "")
        if screenshot:
            print(f"[SCRAPFLY] Screenshot: {screenshot}")

        # Strip HTML comments
        clean = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
        lower = clean.lower()

        # Debug all key signals
        for kw in [
            "unavailable at your location",
            "product not available at the selected pin",
            "add to cart", "buy now",
            "out of stock", "notify me",
            "844505",   # check if pincode was actually applied
        ]:
            idx = lower.find(kw)
            if idx >= 0:
                print(f"[HTML] FOUND '{kw}' → ...{clean[max(0,idx-60):idx+150]}...")
            else:
                print(f"[HTML] NOT FOUND: '{kw}'")

        out_signals = [
            "unavailable at your location",
            "product not available at the selected pin",
            "out of stock", "notify me",
            "currently unavailable", "not serviceable",
        ]
        in_signals = [
            "add to cart", "buy now",
            '"is_in_stock":true', '"is_salable":1',
        ]

        is_out = any(s in lower for s in out_signals)
        is_in  = any(s in lower for s in in_signals)

        # Check if pincode was actually applied — if "844505" not on page,
        # the location wasn't set and result is unreliable
        pincode_applied = PINCODE in lower
        print(f"[HTML] Pincode {PINCODE} found on page: {pincode_applied}")

        if not pincode_applied:
            print("[WARN] Pincode not visible on page — location may not have been set!")

        print(f"[HTML] Out: {[s for s in out_signals if s in lower]}")
        print(f"[HTML] In : {[s for s in in_signals if s in lower]}")

        # Out always wins
        in_stock = is_in and not is_out

        # If pincode wasn't applied and page shows "in stock", don't trust it
        if not pincode_applied and is_in and not is_out:
            print("[WARN] Pincode not applied — treating as UNKNOWN, defaulting to OUT OF STOCK to avoid false alerts")
            in_stock = False

        price = "check site"
        m = re.search(r'"(?:special_price|price)"\s*:\s*"?([\d.]+)"?', html)
        if m and float(m.group(1)) > 1:   # filter out bogus ₹1 / ₹5 prices
            price = f"₹{m.group(1)}"

        return {"in_stock": in_stock, "price": price, "error": None}

    except Exception as e:
        return {"in_stock": False, "price": "N/A", "error": str(e)}


def send_email(price: str):
    subject    = f"🛒 IN STOCK: {PRODUCT_NAME} – JioMart"
    checked_at = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d %b %Y, %I:%M %p IST")
    html_body  = f"""
    <html><body style="font-family:Arial,sans-serif;background:#f5f5f5;padding:20px;">
      <div style="max-width:500px;margin:auto;background:white;border-radius:10px;
                  padding:30px;box-shadow:0 2px 10px rgba(0,0,0,0.1);">
        <h2 style="color:#1a73e8;">🛒 Product Back in Stock!</h2>
        <hr style="border:none;border-top:1px solid #eee;">
        <p><strong>Product:</strong> {PRODUCT_NAME}</p>
        <p><strong>Price:</strong> <span style="color:#e53935;font-size:1.2em;">{price}</span></p>
        <p><strong>Pincode:</strong> {PINCODE}</p>
        <p><strong>Checked at:</strong> {checked_at}</p>
        <a href="{PRODUCT_URL}" style="display:inline-block;margin-top:20px;
           padding:12px 24px;background:#1a73e8;color:white;
           text-decoration:none;border-radius:6px;font-weight:bold;">
          Buy Now on JioMart →
        </a>
      </div>
    </body></html>
    """
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_SENDER
    msg["To"]      = NOTIFY_EMAIL
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_SENDER, GMAIL_PASSWORD)
        server.sendmail(GMAIL_SENDER, NOTIFY_EMAIL, msg.as_string())
    print(f"[EMAIL] ✅ Sent to {NOTIFY_EMAIL}")


def main():
    ist = ZoneInfo("Asia/Kolkata")
    now = datetime.now(ist)
    print(f"[INFO] Current IST time: {now.strftime('%d %b %Y, %I:%M %p IST')}")

    if not (8 <= now.hour < 19):
        print("[INFO] Outside 8 AM – 7 PM IST. Skipping.")
        return

    print(f"[INFO] Checking: '{PRODUCT_NAME}' | Pincode: {PINCODE}")
    result = check_stock()

    if result["error"]:
        print(f"[WARN] {result['error']}")

    status = "✅ IN STOCK" if result["in_stock"] else "❌ OUT OF STOCK"
    print(f"[INFO] Status: {status} | Price: {result['price']}")

    if result["in_stock"]:
        send_email(result["price"])
    else:
        print("[INFO] Not in stock. No email sent.")


if __name__ == "__main__":
    main()
