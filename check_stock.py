"""
JioMart Stock Notifier – ScraperAPI Edition
ScraperAPI handles Akamai/bot bypassing automatically with real residential IPs.
Free tier: 1000 calls/month — more than enough for 30-min checks.
Sign up at: https://www.scraperapi.com (no credit card needed)
"""

import os
import smtplib
import re
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
SCRAPER_API_KEY  = os.environ["SCRAPER_API_KEY"]   # from scraperapi.com dashboard
# ─────────────────────────────────────────────────────────────────────────────

SCRAPER_ENDPOINT = "https://api.scraperapi.com"


def fetch_via_scraperapi(url: str) -> requests.Response:
    """Fetch any URL through ScraperAPI which handles all bot detection."""
    params = {
        "api_key":       SCRAPER_API_KEY,
        "url":           url,
        "country_code":  "in",          # Indian residential IP
        "render":        "false",        # no JS rendering needed — faster
        "keep_headers":  "true",
    }
    resp = requests.get(SCRAPER_ENDPOINT, params=params, timeout=60)
    return resp


def check_stock() -> dict:

    # ── Try 1: JSON API ───────────────────────────────────────────────────────
    pid_match = re.search(r'/(\d+)$', PRODUCT_URL)
    if pid_match:
        pid = pid_match.group(1)
        api_url = f"https://www.jiomart.com/catalog/product/get_product_data/{pid}?pin={PINCODE}"
        try:
            print(f"[API] Fetching product data for {pid} via ScraperAPI...")
            resp = fetch_via_scraperapi(api_url)
            print(f"[API] Status: {resp.status_code}")
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    print(f"[API] Keys: {list(data.keys())}")
                    in_stock = (
                        data.get("is_in_stock", False) or
                        data.get("is_salable", False) or
                        str(data.get("stock_status", "")).upper() == "IN_STOCK"
                    )
                    price = data.get("special_price") or data.get("price", "check site")
                    return {"in_stock": bool(in_stock), "price": f"₹{price}", "error": None}
                except Exception:
                    print("[API] Response not JSON, trying HTML fallback...")
        except Exception as e:
            print(f"[API] Error: {e}")

    # ── Try 2: HTML scrape ────────────────────────────────────────────────────
    print("[HTML] Fetching product page via ScraperAPI...")
    try:
        resp = fetch_via_scraperapi(PRODUCT_URL)
        print(f"[HTML] Status: {resp.status_code} | Size: {len(resp.text)} bytes")

        if resp.status_code != 200:
            return {"in_stock": False, "price": "N/A", "error": f"HTTP {resp.status_code}"}

        text  = resp.text
        # Strip HTML comments — JioMart leaves "Out of Stock" in commented-out
        # markup even when the item IS in stock, causing false negatives.
        text_clean = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
        lower = text_clean.lower()

        # Debug: show context around key terms
        for kw in ["add to cart", "out of stock", "notify me", "is_in_stock", "is_salable"]:
            idx = lower.find(kw)
            if idx >= 0:
                print(f"[HTML] '{kw}' → ...{text_clean[max(0,idx-60):idx+120]}...")
            else:
                print(f"[HTML] '{kw}' → not found after stripping comments")

        out_signals = ["out of stock", "notify me", "currently unavailable", "sold out"]
        in_signals  = ["add to cart", "buy now", '"is_in_stock":true', '"is_salable":1']

        is_out   = any(s in lower for s in out_signals)
        is_in    = any(s in lower for s in in_signals)
        in_stock = is_in and not is_out

        print(f"[HTML] Out : {[s for s in out_signals if s in lower]}")
        print(f"[HTML] In  : {[s for s in in_signals  if s in lower]}")

        price = "check site"
        m = re.search(r'"(?:special_price|price)"\s*:\s*"?([\d.]+)"?', text)
        if m:
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
        print("[INFO] Outside 8 AM – 7 PM IST window. Skipping check to save API credits.")
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
