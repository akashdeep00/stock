"""
JioMart Stock Notifier – requests + Webshare proxy (no browser needed)
Uses rotating residential proxies to bypass Akamai, much faster than Playwright.
"""

import os
import smtplib
import re
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ─── CONFIG ──────────────────────────────────────────────────────────────────
PINCODE      = "844505"
PRODUCT_NAME = "Bikaji Bikaner Chowpati Bhelpuri 110g"
PRODUCT_URL  = "https://www.jiomart.com/p/groceries/bikaji-bikaner-chowpati-bhelpuri-110-g/608498429"

GMAIL_SENDER   = os.environ["GMAIL_SENDER"]
GMAIL_PASSWORD = os.environ["GMAIL_PASSWORD"]
NOTIFY_EMAIL   = os.environ["NOTIFY_EMAIL"]
PROXY_USERNAME = os.environ["PROXY_USERNAME"]
PROXY_PASSWORD = os.environ["PROXY_PASSWORD"]

# Webshare rotating residential proxy
PROXY_URL = f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@p.webshare.io:80"
# ─────────────────────────────────────────────────────────────────────────────

SESSION_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "DNT": "1",
    "Cache-Control": "max-age=0",
}


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(SESSION_HEADERS)
    s.proxies = {"http": PROXY_URL, "https": PROXY_URL}
    return s


def check_stock() -> dict:
    session = make_session()

    # ── Try 1: JSON API with pincode ──────────────────────────────────────────
    # Extract numeric product ID from URL
    pid_match = re.search(r'/(\d+)$', PRODUCT_URL)
    if pid_match:
        pid = pid_match.group(1)
        api_url = f"https://www.jiomart.com/catalog/product/get_product_data/{pid}"
        try:
            print(f"[API] Trying JSON endpoint for product {pid}...")
            resp = session.get(api_url, params={"pin": PINCODE}, timeout=30)
            print(f"[API] Status code: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                print(f"[API] Keys: {list(data.keys())}")
                in_stock = (
                    data.get("is_in_stock", False) or
                    data.get("is_salable", False) or
                    str(data.get("stock_status", "")).upper() == "IN_STOCK"
                )
                price = data.get("special_price") or data.get("price", "check site")
                return {"in_stock": bool(in_stock), "price": f"₹{price}", "error": None}
        except Exception as e:
            print(f"[API] Failed: {e}")

    # ── Try 2: HTML scrape ────────────────────────────────────────────────────
    print("[HTML] Falling back to page scrape...")
    try:
        # First visit homepage to get cookies (makes us look like a real user)
        print("[HTML] Visiting homepage first for cookies...")
        session.get("https://www.jiomart.com", timeout=30)

        print(f"[HTML] Fetching product page: {PRODUCT_URL}")
        resp = session.get(PRODUCT_URL, timeout=30)
        print(f"[HTML] Status code: {resp.status_code}")

        if resp.status_code == 403:
            return {"in_stock": False, "price": "N/A", "error": "403 blocked — proxy may need rotation"}

        html      = resp.text
        text_lower = html.lower()

        print(f"[HTML] Page size: {len(html)} bytes")
        # Print a snippet to debug
        snippet_start = text_lower.find("stock")
        if snippet_start > 0:
            print(f"[HTML] Stock context: ...{html[max(0,snippet_start-100):snippet_start+200]}...")

        out_signals      = ["out of stock", "notify me", "currently unavailable", "sold out"]
        in_stock_signals = ["add to cart", "buy now", "add to bag", '"is_in_stock":true', '"is_salable":1']

        is_out   = any(sig in text_lower for sig in out_signals)
        is_in    = any(sig in text_lower for sig in in_stock_signals)
        in_stock = is_in and not is_out

        print(f"[HTML] Out signals : {[s for s in out_signals if s in text_lower]}")
        print(f"[HTML] In signals  : {[s for s in in_stock_signals if s in text_lower]}")

        # Price from JSON embedded in page
        price = "check site"
        price_match = re.search(r'"price"\s*:\s*"?([\d.]+)"?', html)
        if price_match:
            price = f"₹{price_match.group(1)}"

        return {"in_stock": in_stock, "price": price, "error": None}

    except Exception as e:
        return {"in_stock": False, "price": "N/A", "error": str(e)}


def send_email(price: str):
    subject    = f"🛒 IN STOCK: {PRODUCT_NAME} – JioMart"
    checked_at = datetime.now().strftime("%d %b %Y, %I:%M %p")
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
    print(f"[EMAIL] ✅ Notification sent to {NOTIFY_EMAIL}")


def main():
    print(f"[INFO] Checking stock for '{PRODUCT_NAME}' at pincode {PINCODE}...")
    result = check_stock()
    if result["error"]:
        print(f"[WARN] {result['error']}")
    status = "✅ IN STOCK" if result["in_stock"] else "❌ OUT OF STOCK"
    print(f"[INFO] Status: {status} | Price: {result['price']}")
    if result["in_stock"]:
        print("[INFO] Sending email notification...")
        send_email(result["price"])
    else:
        print("[INFO] Not in stock. No email sent.")


if __name__ == "__main__":
    main()
