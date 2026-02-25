"""
JioMart Stock Notifier – Scrapfly + correct pincode selector
"""

import os
import smtplib
import re
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from zoneinfo import ZoneInfo
from scrapfly import ScrapeConfig, ScrapflyClient

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
    client = ScrapflyClient(key=SCRAPFLY_API_KEY)

    # ── Step 1: Use correct selector #rel_pincode ─────────────────────────────
    print(f"[SCRAPFLY] Loading page and entering pincode via #rel_pincode...")
    try:
        result = client.scrape(ScrapeConfig(
            url=PRODUCT_URL,
            asp=True,
            render_js=True,
            country="in",
            js_scenario=[
                {"wait": 3000},
                {"fill": {"selector": "#rel_pincode", "value": PINCODE, "clear": True}},
                {"execute": {"script": "document.querySelector('#rel_pincode').dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', keyCode: 13, bubbles: true})); document.querySelector('#rel_pincode').dispatchEvent(new Event('input', {bubbles: true}));"}},
                {"click": {"selector": ".jm-btn.primary, button[class*='apply'], .pincode-btn", "ignore_if_not_exists": True}},
                {"wait_for_navigation": {"timeout": 5000}},
                {"wait": 3000},
            ],
        ))

        html  = result.scrape_result["content"]
        clean = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
        lower = clean.lower()

        print(f"[SCRAPFLY] Page size: {len(html)} bytes")
        print(f"[CHECK] Pincode on page: {PINCODE in lower}")

        # ── Step 2: Extract the MST API URL from hidden fields and call it ────
        # JioMart uses /mst/rest/v1/{product_id}/?pincode=X to check availability
        sku_match = re.search(r'id="sku_val" value="(\d+)"', html)
        sku = sku_match.group(1) if sku_match else None
        print(f"[API] SKU found: {sku}")

        if sku:
            mst_url = f"https://www.jiomart.com/mst/rest/v1/{sku}/?pincode={PINCODE}"
            print(f"[API] Calling MST API: {mst_url}")
            try:
                api_result = client.scrape(ScrapeConfig(
                    url=mst_url,
                    asp=True,
                    country="in",
                ))
                api_content = api_result.scrape_result["content"]
                print(f"[API] Response: {api_content[:500]}")
                try:
                    data = __import__("json").loads(api_content)
                    print(f"[API] Keys: {list(data.keys())}")
                    # Check serviceability
                    serviceable = data.get("serviceable", data.get("pincode_serviceable", True))
                    in_stock    = data.get("is_in_stock", data.get("is_salable", False))
                    if serviceable is False:
                        return {"in_stock": False, "price": "N/A", "error": None}
                    if in_stock is not None:
                        price = data.get("special_price") or data.get("price", "check site")
                        return {"in_stock": bool(in_stock) and bool(serviceable),
                                "price": f"₹{price}", "error": None}
                except Exception as e:
                    print(f"[API] Parse error: {e}")
            except Exception as e:
                print(f"[API] Error: {e}")

        # ── Step 3: Fallback — read page text signals ─────────────────────────
        for kw in ["unavailable at your location",
                   "product not available at the selected pin",
                   "add to cart", "out of stock", "notify me"]:
            idx = lower.find(kw)
            if idx >= 0:
                print(f"[HTML] FOUND '{kw}' → ...{clean[max(0,idx-40):idx+120]}...")
            else:
                print(f"[HTML] NOT FOUND: '{kw}'")

        out_signals = [
            "unavailable at your location",
            "product not available at the selected pin",
            "out of stock", "notify me", "currently unavailable",
        ]
        in_signals = ["add to cart", "buy now"]

        is_out   = any(s in lower for s in out_signals)
        is_in    = any(s in lower for s in in_signals)
        in_stock = is_in and not is_out

        # Only trust result if pincode was applied
        if not (PINCODE in lower) and in_stock:
            print("[WARN] Pincode not on page — not trusting IN STOCK result")
            in_stock = False

        price = "check site"
        m = re.search(r'id="selling_price_val" value="([\d.]+)"', html)
        if m and float(m.group(1)) > 5:
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
