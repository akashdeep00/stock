"""
JioMart Stock Notifier – GitHub Actions + Webshare Proxy
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
PROXY_USERNAME = os.environ["PROXY_USERNAME"]   # proxy-specific username from Webshare Proxy List
PROXY_PASSWORD = os.environ["PROXY_PASSWORD"]   # proxy-specific password from Webshare Proxy List

# Webshare backbone rotating proxy — port 3128 works best for HTTPS tunneling
PROXY_HOST = "p.webshare.io"
PROXY_PORT = "3128"
PROXY_URL  = f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT}"
PROXIES    = {"http": PROXY_URL, "https": PROXY_URL}
# ─────────────────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


def test_proxy() -> bool:
    """Verify proxy is working by checking our outbound IP."""
    try:
        resp = requests.get(
            "https://ipv4.webshare.io/",
            proxies=PROXIES,
            timeout=15,
        )
        ip = resp.text.strip()
        print(f"[PROXY] ✅ Working — outbound IP: {ip}")
        return True
    except Exception as e:
        print(f"[PROXY] ❌ Failed: {e}")
        return False


def check_stock() -> dict:
    session = requests.Session()
    session.headers.update(HEADERS)
    session.proxies.update(PROXIES)

    # ── Try JSON API first ────────────────────────────────────────────────────
    pid_match = re.search(r'/(\d+)$', PRODUCT_URL)
    if pid_match:
        pid = pid_match.group(1)
        api_url = f"https://www.jiomart.com/catalog/product/get_product_data/{pid}"
        try:
            print(f"[API] Querying product {pid} for pincode {PINCODE}...")
            resp = session.get(api_url, params={"pin": PINCODE}, timeout=30)
            print(f"[API] Status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                print(f"[API] Response keys: {list(data.keys())}")
                in_stock = (
                    data.get("is_in_stock", False) or
                    data.get("is_salable", False) or
                    str(data.get("stock_status", "")).upper() == "IN_STOCK"
                )
                price = data.get("special_price") or data.get("price", "check site")
                return {"in_stock": bool(in_stock), "price": f"₹{price}", "error": None}
        except Exception as e:
            print(f"[API] Error: {e}")

    # ── Fallback: scrape HTML ─────────────────────────────────────────────────
    print("[HTML] Scraping product page...")
    try:
        # Get homepage cookies first
        session.get("https://www.jiomart.com", timeout=20)

        resp = session.get(PRODUCT_URL, timeout=30)
        print(f"[HTML] Status: {resp.status_code} | Size: {len(resp.text)} bytes")

        if resp.status_code != 200:
            return {"in_stock": False, "price": "N/A", "error": f"HTTP {resp.status_code}"}

        text_lower = resp.text.lower()

        # Print a small snapshot around key stock terms
        for keyword in ["add to cart", "out of stock", "notify me", "is_in_stock", "is_salable"]:
            idx = text_lower.find(keyword)
            if idx >= 0:
                print(f"[HTML] Found '{keyword}' → ...{resp.text[max(0,idx-50):idx+100]}...")

        out_signals      = ["out of stock", "notify me", "currently unavailable", "sold out"]
        in_stock_signals = ["add to cart", "buy now", '"is_in_stock":true', '"is_salable":1']

        is_out   = any(s in text_lower for s in out_signals)
        is_in    = any(s in text_lower for s in in_stock_signals)
        in_stock = is_in and not is_out

        print(f"[HTML] Out signals : {[s for s in out_signals if s in text_lower]}")
        print(f"[HTML] In  signals : {[s for s in in_stock_signals if s in text_lower]}")

        price = "check site"
        m = re.search(r'"(?:special_price|price)"\s*:\s*"?([\d.]+)"?', resp.text)
        if m:
            price = f"₹{m.group(1)}"

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
    print(f"[EMAIL] ✅ Sent to {NOTIFY_EMAIL}")


def main():
    print(f"[INFO] Checking: '{PRODUCT_NAME}' | Pincode: {PINCODE}")

    # Always test proxy first
    if not test_proxy():
        print("[ERROR] Proxy not working — check PROXY_USERNAME and PROXY_PASSWORD secrets")
        return

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
