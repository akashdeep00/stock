"""
JioMart Stock Notifier – Scrapfly Edition
Scrapfly handles Akamai bypass automatically (97% success rate).
Free plan: 1,000 credits/month, no credit card needed.
Sign up: https://scrapfly.io
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
PRODUCT_NAME = "onion-1-kg-pack"
PRODUCT_URL  = "https://www.jiomart.com/p/groceries/onion-1-kg-pack/611163418"

GMAIL_SENDER      = os.environ["GMAIL_SENDER"]
GMAIL_PASSWORD    = os.environ["GMAIL_PASSWORD"]
NOTIFY_EMAIL      = os.environ["NOTIFY_EMAIL"]
SCRAPFLY_API_KEY  = os.environ["SCRAPFLY_API_KEY"]   # from scrapfly.io dashboard
# ─────────────────────────────────────────────────────────────────────────────


def fetch(url: str) -> requests.Response:
    """Fetch via Scrapfly with Akamai bypass + JS rendering + Indian IP."""
    params = {
        "key":             SCRAPFLY_API_KEY,
        "url":             url,
        "asp":             "true",      # Anti-Scraping Protection — bypasses Akamai
        "render_js":       "true",      # Execute JavaScript
        "country":         "in",        # Indian residential IP
        "cookies":         f"delivery_pin={PINCODE}; pincode={PINCODE}",
    }
    return requests.get("https://api.scrapfly.io/scrape", params=params, timeout=120)


def check_stock() -> dict:
    pid_match = re.search(r'/(\d+)$', PRODUCT_URL)
    if not pid_match:
        return {"in_stock": False, "price": "N/A", "error": "Cannot extract product ID"}
    pid = pid_match.group(1)

    # ── Try 1: Internal JSON API ──────────────────────────────────────────────
    api_url = f"https://www.jiomart.com/catalog/product/get_product_data/{pid}?pin={PINCODE}"
    try:
        print(f"[API] Querying product {pid} for pincode {PINCODE}...")
        resp = fetch(api_url)
        print(f"[API] HTTP: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            # Scrapfly wraps response in a result object
            content = data.get("result", {}).get("content", "")
            print(f"[API] Content preview: {content[:300]}")
            try:
                product = __import__("json").loads(content)
                print(f"[API] Product keys: {list(product.keys())}")
                serviceable = (
                    product.get("pincode_serviceable", True) and
                    product.get("serviceable", True)
                )
                in_stock = serviceable and (
                    product.get("is_in_stock", False) or
                    product.get("is_salable", False) or
                    str(product.get("stock_status", "")).upper() == "IN_STOCK"
                )
                price = product.get("special_price") or product.get("price", "check site")
                return {"in_stock": bool(in_stock), "price": f"₹{price}", "error": None}
            except Exception as e:
                print(f"[API] JSON parse error: {e}")
    except Exception as e:
        print(f"[API] Error: {e}")

    # ── Try 2: HTML page scrape ───────────────────────────────────────────────
    print("[HTML] Fetching rendered product page via Scrapfly...")
    try:
        resp = fetch(PRODUCT_URL)
        print(f"[HTML] HTTP: {resp.status_code}")

        if resp.status_code != 200:
            return {"in_stock": False, "price": "N/A", "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}

        data    = resp.json()
        html    = data.get("result", {}).get("content", resp.text)
        print(f"[HTML] Page size: {len(html)} bytes")

        clean = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
        lower = clean.lower()

        for kw in [
            "unavailable at your location",
            "product not available at the selected pin",
            "add to cart", "buy now", "out of stock", "notify me",
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
        in_signals = ["add to cart", "buy now", '"is_in_stock":true', '"is_salable":1']

        is_out   = any(s in lower for s in out_signals)
        is_in    = any(s in lower for s in in_signals)
        in_stock = is_in and not is_out

        print(f"[HTML] Out: {[s for s in out_signals if s in lower]}")
        print(f"[HTML] In : {[s for s in in_signals if s in lower]}")

        price = "check site"
        m = re.search(r'"(?:special_price|price)"\s*:\s*"?([\d.]+)"?', html)
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
