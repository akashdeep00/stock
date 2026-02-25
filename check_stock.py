"""
JioMart Stock Notifier – GitHub Actions Edition
Checks stock for a pincode and sends Gmail alert if available.
"""

import os
import smtplib
import requests
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ─── CONFIG (set these as GitHub Secrets) ────────────────────────────────────
PRODUCT_ID   = "590011678"
PINCODE      = "844505"
PRODUCT_NAME = "Onion 1 Kg Pack"
PRODUCT_URL  = "https://www.jiomart.com/p/groceries/onion-1-kg-pack/611163418"

GMAIL_SENDER   = os.environ["GMAIL_SENDER"]    # your Gmail address
GMAIL_PASSWORD = os.environ["GMAIL_PASSWORD"]  # Gmail App Password
NOTIFY_EMAIL   = os.environ["NOTIFY_EMAIL"]    # email to receive alerts (can be same)
# ─────────────────────────────────────────────────────────────────────────────


def check_stock() -> dict:
    """Check product availability via JioMart API, with HTML scrape fallback."""
    url = f"https://www.jiomart.com/catalog/product/get_product_data/{PRODUCT_ID}"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-IN,en;q=0.9",
        "Referer": PRODUCT_URL,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "X-Requested-With": "XMLHttpRequest",
    }

    try:
        resp = requests.get(url, headers=headers, params={"pin": PINCODE}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        print(f"[API] Response: {json.dumps(data, indent=2)[:500]}")

        in_stock = (
            data.get("is_in_stock", False)
            or data.get("is_salable", False)
            or data.get("stock_status", "") == "IN_STOCK"
        )
        price = data.get("special_price") or data.get("price", "N/A")
        return {"in_stock": bool(in_stock), "price": f"₹{price}", "error": None}

    except Exception as api_err:
        print(f"[API] Failed: {api_err} — trying HTML fallback...")
        return _fallback_scrape(api_err)


def _fallback_scrape(original_error) -> dict:
    """Scrape the product page to detect out-of-stock signals."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-IN,en;q=0.9",
        }
        resp = requests.get(f"{PRODUCT_URL}?pin={PINCODE}", headers=headers, timeout=15)
        resp.raise_for_status()
        html = resp.text.lower()

        out_signals = ["out of stock", "notify me", "currently unavailable", "sold out"]
        in_stock = not any(sig in html for sig in out_signals)

        # Try to extract price from HTML
        import re
        price_match = re.search(r'"price"\s*:\s*"?([\d.]+)"?', html)
        price = f"₹{price_match.group(1)}" if price_match else "check site"

        return {"in_stock": in_stock, "price": price, "error": f"Fallback used: {original_error}"}
    except Exception as e:
        return {"in_stock": False, "price": "N/A", "error": str(e)}


def send_email(price: str):
    """Send a nicely formatted HTML email via Gmail SMTP."""
    subject = f"🛒 IN STOCK: {PRODUCT_NAME} – JioMart"
    checked_at = datetime.now().strftime("%d %b %Y, %I:%M %p")

    html_body = f"""
    <html><body style="font-family: Arial, sans-serif; background: #f5f5f5; padding: 20px;">
      <div style="max-width: 500px; margin: auto; background: white; border-radius: 10px;
                  padding: 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
        <h2 style="color: #1a73e8;">🛒 Product Back in Stock!</h2>
        <hr style="border: none; border-top: 1px solid #eee;">

        <p><strong>Product:</strong> {PRODUCT_NAME}</p>
        <p><strong>Price:</strong> <span style="color: #e53935; font-size: 1.2em;">{price}</span></p>
        <p><strong>Pincode:</strong> {PINCODE}</p>
        <p><strong>Checked at:</strong> {checked_at}</p>

        <a href="{PRODUCT_URL}" style="display: inline-block; margin-top: 20px;
           padding: 12px 24px; background: #1a73e8; color: white;
           text-decoration: none; border-radius: 6px; font-weight: bold;">
          Buy Now on JioMart →
        </a>

        <p style="margin-top: 30px; font-size: 0.8em; color: #999;">
          This alert was sent by your JioMart Stock Notifier (GitHub Actions).
        </p>
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
