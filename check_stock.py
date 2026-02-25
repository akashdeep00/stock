"""
JioMart Stock Notifier – ScraperAPI + JS Instruction Edition
Uses ScraperAPI to interact with the page (type pincode, wait for response)
before scraping the stock status.
"""

import os
import smtplib
import re
import requests
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from zoneinfo import ZoneInfo

# ─── CONFIG ──────────────────────────────────────────────────────────────────
PINCODE      = "844505"
PRODUCT_NAME = "Bikaji Bikaner Chowpati Bhelpuri 110g"
PRODUCT_URL  = "https://www.jiomart.com/p/groceries/bikaji-bikaner-chowpati-bhelpuri-110-g/608498429"

GMAIL_SENDER    = os.environ["GMAIL_SENDER"]
GMAIL_PASSWORD  = os.environ["GMAIL_PASSWORD"]
NOTIFY_EMAIL    = os.environ["NOTIFY_EMAIL"]
SCRAPER_API_KEY = os.environ["SCRAPER_API_KEY"]

SCRAPER_ENDPOINT = "https://api.scraperapi.com/structured/html"
# ─────────────────────────────────────────────────────────────────────────────


def check_stock() -> dict:
    pid_match = re.search(r'/(\d+)$', PRODUCT_URL)
    if not pid_match:
        return {"in_stock": False, "price": "N/A", "error": "Cannot extract product ID"}
    pid = pid_match.group(1)

    # ── Approach 1: ScraperAPI with JS instructions to enter pincode ──────────
    # ScraperAPI supports structured instructions to interact with pages
    print("[SCRAPER] Fetching page with pincode interaction...")
    try:
        payload = {
            "api_key":      SCRAPER_API_KEY,
            "url":          PRODUCT_URL,
            "country_code": "in",
            "render":       True,
            "instructions": [
                # Wait for page to load
                {"wait": 3000},
                # Click the pincode field if it exists
                {"click": "input[placeholder*='PIN'], input[placeholder*='pincode'], .pincode-input"},
                {"wait": 500},
                # Clear and type pincode
                {"fill": ["input[placeholder*='PIN'], input[placeholder*='pincode'], .pincode-input", PINCODE]},
                {"wait": 500},
                {"press": ["input[placeholder*='PIN'], input[placeholder*='pincode'], .pincode-input", "Enter"]},
                # Wait for availability to update
                {"wait": 4000},
            ]
        }
        resp = requests.post(
            "https://api.scraperapi.com/",
            json=payload,
            timeout=120
        )
        print(f"[SCRAPER] Status: {resp.status_code} | Size: {len(resp.text)} bytes")

        if resp.status_code == 200:
            result = _parse_html(resp.text)
            if result is not None:
                return result
    except Exception as e:
        print(f"[SCRAPER] Error: {e}")

    # ── Approach 2: Simple GET with render (fallback) ─────────────────────────
    print("[FALLBACK] Simple rendered GET...")
    try:
        params = {
            "api_key":      SCRAPER_API_KEY,
            "url":          PRODUCT_URL,
            "country_code": "in",
            "render":       "true",
        }
        resp = requests.get("https://api.scraperapi.com/", params=params, timeout=120)
        print(f"[FALLBACK] Status: {resp.status_code} | Size: {len(resp.text)} bytes")
        if resp.status_code == 200:
            result = _parse_html(resp.text)
            if result is not None:
                return result
    except Exception as e:
        print(f"[FALLBACK] Error: {e}")

    return {"in_stock": False, "price": "N/A", "error": "All methods failed"}


def _parse_html(html: str) -> dict | None:
    """Parse JioMart HTML to determine stock status."""

    # Strip HTML comments
    clean = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
    lower = clean.lower()

    # Debug all relevant keywords
    for kw in [
        "unavailable at your location",
        "product not available at the selected pin",
        "add to cart", "buy now",
        "out of stock", "notify me",
        "serviceable", "is_in_stock", "is_salable",
    ]:
        idx = lower.find(kw)
        if idx >= 0:
            print(f"[PARSE] FOUND '{kw}' → ...{clean[max(0,idx-60):idx+150]}...")
        else:
            print(f"[PARSE] NOT FOUND: '{kw}'")

    out_signals = [
        "unavailable at your location",
        "product not available at the selected pin",
        "out of stock", "notify me",
        "currently unavailable", "sold out",
        "not serviceable",
    ]
    in_signals = [
        "add to cart", "buy now",
        '"is_in_stock":true', '"is_salable":1',
    ]

    is_out = any(s in lower for s in out_signals)
    is_in  = any(s in lower for s in in_signals)

    print(f"[PARSE] Out matched: {[s for s in out_signals if s in lower]}")
    print(f"[PARSE] In  matched: {[s for s in in_signals if s in lower]}")

    # Out always wins
    in_stock = is_in and not is_out

    price = "check site"
    m = re.search(r'"(?:special_price|price)"\s*:\s*"?([\d.]+)"?', html)
    if m:
        price = f"₹{m.group(1)}"

    return {"in_stock": in_stock, "price": price, "error": None}


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
        print("[INFO] Outside 8 AM – 7 PM IST window. Skipping to save API credits.")
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
