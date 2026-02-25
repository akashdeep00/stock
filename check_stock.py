"""
JioMart Stock Notifier – Playwright + Webshare Proxy + Network Intercept
Uses residential proxy to bypass Akamai, then intercepts JioMart's internal
XHR calls to get real pincode-level stock data.
"""

import os
import smtplib
import re
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ─── CONFIG ──────────────────────────────────────────────────────────────────
PINCODE      = "844505"
PRODUCT_NAME = "Bikaji Bikaner Chowpati Bhelpuri 110g"
PRODUCT_URL  = "https://www.jiomart.com/p/groceries/bikaji-bikaner-chowpati-bhelpuri-110-g/608498429"

GMAIL_SENDER    = os.environ["GMAIL_SENDER"]
GMAIL_PASSWORD  = os.environ["GMAIL_PASSWORD"]
NOTIFY_EMAIL    = os.environ["NOTIFY_EMAIL"]
PROXY_USERNAME  = os.environ["PROXY_USERNAME"]
PROXY_PASSWORD  = os.environ["PROXY_PASSWORD"]
# ─────────────────────────────────────────────────────────────────────────────


def check_stock() -> dict:
    captured = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            proxy={
                "server":   "http://p.webshare.io:3128",
                "username": PROXY_USERNAME,
                "password": PROXY_PASSWORD,
            },
            args=["--no-sandbox", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            viewport={"width": 1280, "height": 800},
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
            "window.chrome = { runtime: {} };"
        )
        page = context.new_page()

        # ── Intercept XHR responses ───────────────────────────────────────────
        def handle_response(response):
            url = response.url.lower()
            if any(kw in url for kw in [
                "get_product_data", "availability", "serviceable",
                "pincode", "stock", "catalog/product",
            ]):
                try:
                    body = response.json()
                    print(f"[XHR] {response.url}")
                    print(f"[XHR] Body: {json.dumps(body)[:600]}")
                    captured.append(body)
                except Exception:
                    pass

        page.on("response", handle_response)

        try:
            print("[BROWSER] Loading product page via proxy...")
            page.goto(PRODUCT_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(4000)

            # Check if blocked
            body_text = page.evaluate("() => document.body?.innerText || ''")
            if "access denied" in body_text.lower():
                browser.close()
                return {"in_stock": False, "price": "N/A",
                        "error": "Akamai blocked — proxy IP flagged, try rotating"}

            # ── Enter pincode ─────────────────────────────────────────────────
            pin_entered = False
            selectors = [
                "input[placeholder*='PIN' i]",
                "input[placeholder*='pincode' i]",
                "input[placeholder*='Enter PIN' i]",
                ".pincode-input input",
                "#pincode-input",
                "input[name='pincode']",
            ]
            for sel in selectors:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=2000):
                        print(f"[BROWSER] Pincode input found: {sel}")
                        el.click()
                        page.wait_for_timeout(300)
                        el.fill(PINCODE)
                        page.keyboard.press("Enter")
                        print(f"[BROWSER] Entered {PINCODE}, waiting for XHR...")
                        page.wait_for_timeout(6000)
                        pin_entered = True
                        break
                except PWTimeout:
                    continue

            if not pin_entered:
                # Try clicking the "Deliver to" / pincode section to open the modal
                print("[BROWSER] Trying to open pincode modal...")
                for trigger in ["text=Enter PIN", "text=Change", "[class*='pincode']",
                                 "[class*='deliver']", "text=Deliver to"]:
                    try:
                        page.locator(trigger).first.click(timeout=2000)
                        page.wait_for_timeout(1000)
                        # Now try inputs again
                        for sel in selectors:
                            try:
                                el = page.locator(sel).first
                                if el.is_visible(timeout=2000):
                                    el.fill(PINCODE)
                                    page.keyboard.press("Enter")
                                    page.wait_for_timeout(6000)
                                    pin_entered = True
                                    break
                            except PWTimeout:
                                continue
                        if pin_entered:
                            break
                    except PWTimeout:
                        continue

            print(f"[BROWSER] Pincode entered: {pin_entered}")
            print(f"[BROWSER] XHR calls captured: {len(captured)}")

            # ── Parse captured XHR ────────────────────────────────────────────
            for data in captured:
                print(f"[XHR PARSE] {data}")
                # Explicit serviceability check
                if data.get("pincode_serviceable") is False or \
                   data.get("serviceable") is False or \
                   data.get("is_serviceable") is False:
                    browser.close()
                    return {"in_stock": False, "price": "N/A", "error": None}
                if data.get("is_in_stock") is True or data.get("is_salable") is True:
                    price = data.get("special_price") or data.get("price", "check site")
                    browser.close()
                    return {"in_stock": True, "price": f"₹{price}", "error": None}
                if data.get("is_in_stock") is False or data.get("is_salable") is False:
                    browser.close()
                    return {"in_stock": False, "price": "N/A", "error": None}

            # ── Fallback: read visible page text ──────────────────────────────
            print("[BROWSER] Falling back to page text...")
            full_text  = page.evaluate("() => document.body?.innerText || ''")
            text_lower = full_text.lower()
            print(f"[PAGE TEXT]\n{full_text[:2000]}\n")

            out_signals = [
                "unavailable at your location",
                "product not available at the selected pin",
                "out of stock", "notify me",
                "currently unavailable", "not serviceable",
            ]
            in_signals = ["add to cart", "buy now"]

            is_out = any(s in text_lower for s in out_signals)
            is_in  = any(s in text_lower for s in in_signals)

            print(f"[TEXT] Out: {[s for s in out_signals if s in text_lower]}")
            print(f"[TEXT] In : {[s for s in in_signals  if s in text_lower]}")

            browser.close()
            return {"in_stock": is_in and not is_out, "price": "check site", "error": None}

        except Exception as e:
            try:
                browser.close()
            except Exception:
                pass
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
