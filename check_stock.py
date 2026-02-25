"""
JioMart Stock Notifier – Scrapfly + MST API
Calls JioMart's internal MST API directly (found from page hidden fields)
to get pincode-level stock without any JS interaction needed.
"""

import os
import smtplib
import re
import json
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

    # ── Step 1: Load product page to extract SKU and selling price ────────────
    print("[SCRAPFLY] Loading product page to extract SKU...")
    try:
        result = client.scrape(ScrapeConfig(
            url=PRODUCT_URL,
            asp=True,
            render_js=False,   # no JS needed just to get the SKU
            country="in",
        ))
        html = result.scrape_result["content"]
        print(f"[PAGE] Size: {len(html)} bytes")

        # Extract SKU from hidden field: <input value="490070538" id="vari_set_name">
        sku_match  = re.search(r'id="vari_set_name"[^>]*value="(\d+)"', html) or \
                     re.search(r'value="(\d+)"[^>]*id="vari_set_name"', html)
        price_match = re.search(r'id="selling_price_val"[^>]*value="([\d.]+)"', html) or \
                      re.search(r'value="([\d.]+)"[^>]*id="selling_price_val"', html)

        sku   = sku_match.group(1)   if sku_match   else None
        price = price_match.group(1) if price_match else None
        print(f"[PAGE] SKU: {sku} | Selling price: {price}")

    except Exception as e:
        return {"in_stock": False, "price": "N/A", "error": f"Page load error: {e}"}

    if not sku:
        return {"in_stock": False, "price": "N/A", "error": "Could not extract SKU"}

    # ── Step 2: Call MST API directly with pincode ────────────────────────────
    # This is JioMart's internal pincode availability API found in page hidden fields
    mst_url = f"https://www.jiomart.com/mst/rest/v1/{sku}/?pincode={PINCODE}"
    print(f"[MST API] Calling: {mst_url}")
    try:
        api_result = client.scrape(ScrapeConfig(
            url=mst_url,
            asp=True,
            render_js=False,
            country="in",
        ))
        content = api_result.scrape_result["content"]
        print(f"[MST API] Response: {content[:500]}")

        data = json.loads(content)
        print(f"[MST API] Keys: {list(data.keys())}")

        # Check all possible serviceability / stock fields
        serviceable = data.get("serviceable",
                     data.get("pincode_serviceable",
                     data.get("is_serviceable", True)))

        in_stock_val = data.get("is_in_stock",
                       data.get("is_salable",
                       data.get("available", None)))

        print(f"[MST API] serviceable={serviceable} | in_stock={in_stock_val}")

        if serviceable is False:
            return {"in_stock": False, "price": f"₹{price}" if price else "N/A", "error": None}

        if in_stock_val is not None:
            final_price = data.get("special_price") or data.get("price") or price or "check site"
            return {
                "in_stock": bool(in_stock_val) and bool(serviceable),
                "price": f"₹{final_price}",
                "error": None
            }

        # If API doesn't give clear answer, check message field
        msg = str(data).lower()
        if "unavailable" in msg or "not serviceable" in msg:
            return {"in_stock": False, "price": "N/A", "error": None}

        return {"in_stock": False, "price": "N/A",
                "error": f"Unclear API response: {content[:200]}"}

    except json.JSONDecodeError:
        # API returned HTML instead of JSON — check for stock signals
        lower = content.lower()
        print(f"[MST API] Non-JSON response preview: {content[:300]}")
        if "unavailable" in lower or "not serviceable" in lower:
            return {"in_stock": False, "price": "N/A", "error": None}
        return {"in_stock": False, "price": "N/A",
                "error": f"Non-JSON response from MST API"}
    except Exception as e:
        return {"in_stock": False, "price": "N/A", "error": f"MST API error: {e}"}


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
