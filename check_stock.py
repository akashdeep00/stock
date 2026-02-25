"""
JioMart Stock Notifier – GitHub Actions + Webshare Proxy Edition
Routes through a residential proxy to bypass Akamai block on GitHub IPs.
"""

import os
import smtplib
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ─── CONFIG ──────────────────────────────────────────────────────────────────
PINCODE      = "844505"
PRODUCT_NAME = "Bikaji Bikaner Chowpati Bhelpuri 110g"
PRODUCT_URL  = "https://www.jiomart.com/p/groceries/bikaji-bikaner-chowpati-bhelpuri-110-g/608498429"

GMAIL_SENDER    = os.environ["GMAIL_SENDER"]
GMAIL_PASSWORD  = os.environ["GMAIL_PASSWORD"]
NOTIFY_EMAIL    = os.environ["NOTIFY_EMAIL"]
PROXY_USERNAME  = os.environ["PROXY_USERNAME"]   # from Webshare dashboard
PROXY_PASSWORD  = os.environ["PROXY_PASSWORD"]   # from Webshare dashboard

# Webshare rotating proxy endpoint (same for all free accounts)
PROXY_SERVER    = "p.webshare.io"
PROXY_PORT      = 80
# ─────────────────────────────────────────────────────────────────────────────

STEALTH_JS = """
() => {
    Object.defineProperty(navigator, 'webdriver',     { get: () => undefined });
    Object.defineProperty(navigator, 'plugins',       { get: () => [1,2,3,4,5] });
    Object.defineProperty(navigator, 'languages',     { get: () => ['en-IN','en-US','en'] });
    Object.defineProperty(navigator, 'maxTouchPoints',{ get: () => 1 });
    Object.defineProperty(screen, 'width',            { get: () => 1920 });
    Object.defineProperty(screen, 'height',           { get: () => 1080 });
    window.chrome = { runtime: {} };
}
"""


def check_stock() -> dict:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            proxy={
                "server":   f"http://{PROXY_SERVER}:{PROXY_PORT}",
                "username": PROXY_USERNAME,
                "password": PROXY_PASSWORD,
            },
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--window-size=1920,1080",
            ],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            viewport={"width": 1920, "height": 1080},
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
            },
        )
        context.add_init_script(STEALTH_JS)
        page = context.new_page()

        try:
            print("[BROWSER] Loading JioMart product page via proxy...")
            page.goto(PRODUCT_URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(5000)

            # ── Pincode entry ─────────────────────────────────────────────
            try:
                pin_input = page.locator(
                    "input[placeholder*='PIN'], input[placeholder*='pin'], "
                    "input[placeholder*='Pincode'], #pincode-input, input[name='pincode']"
                ).first
                if pin_input.is_visible(timeout=4000):
                    print(f"[BROWSER] Entering pincode {PINCODE}...")
                    pin_input.click()
                    page.wait_for_timeout(300)
                    pin_input.fill(PINCODE)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(4000)
                else:
                    print("[BROWSER] No pincode input visible.")
            except PlaywrightTimeout:
                print("[BROWSER] Pincode input timed out.")

            # ── Debug snapshot ────────────────────────────────────────────
            full_text = page.inner_text("body")
            print("\n[DEBUG] ── Page text snapshot (first 2000 chars) ──")
            print(full_text[:2000])
            print("[DEBUG] ── End snapshot ──\n")
            text_lower = full_text.lower()

            if "access denied" in text_lower:
                browser.close()
                return {"in_stock": False, "price": "N/A", "error": "Still blocked — check proxy credentials"}

            # ── Stock detection ───────────────────────────────────────────
            out_signals      = ["out of stock", "notify me", "currently unavailable", "sold out"]
            in_stock_signals = ["add to cart", "buy now", "add to bag"]

            btn_visible = page.locator(
                "button:has-text('Add to Cart'), button:has-text('ADD TO CART'), "
                "button:has-text('Buy Now'), button:has-text('BUY NOW')"
            ).count() > 0

            is_out   = any(sig in text_lower for sig in out_signals)
            is_in    = any(sig in text_lower for sig in in_stock_signals) or btn_visible
            in_stock = is_in and not is_out

            print(f"[BROWSER] Out signals      : {[s for s in out_signals if s in text_lower]}")
            print(f"[BROWSER] In signals       : {[s for s in in_stock_signals if s in text_lower]}")
            print(f"[BROWSER] Cart btn visible : {btn_visible}")

            # ── Price extraction ──────────────────────────────────────────
            price = "check site"
            price_match = re.search(r'₹\s*([\d,]+)', full_text)
            if price_match:
                price = f"₹{price_match.group(1)}"

            browser.close()
            return {"in_stock": in_stock, "price": price, "error": None}

        except Exception as e:
            browser.close()
            return {"in_stock": False, "price": "N/A", "error": str(e)}


def send_email(price: str):
    subject = f"🛒 IN STOCK: {PRODUCT_NAME} – JioMart"
    checked_at = datetime.now().strftime("%d %b %Y, %I:%M %p")
    html_body = f"""
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
