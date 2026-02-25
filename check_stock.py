"""
JioMart Stock Notifier – GitHub Actions Edition
Uses Playwright (headless browser) to bypass JioMart's bot protection.
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
PRODUCT_NAME = "Onion 1 Kg Pack"
PRODUCT_URL  = "https://www.jiomart.com/p/groceries/onion-1-kg-pack/611163418"

GMAIL_SENDER   = os.environ["GMAIL_SENDER"]
GMAIL_PASSWORD = os.environ["GMAIL_PASSWORD"]
NOTIFY_EMAIL   = os.environ["NOTIFY_EMAIL"]
# ─────────────────────────────────────────────────────────────────────────────


def check_stock() -> dict:
    """Use a headless Chromium browser to load the JioMart page with the pincode set."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="en-IN",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        try:
            # Step 1: Open the product page
            print(f"[BROWSER] Loading product page...")
            page.goto(PRODUCT_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            # Step 2: Enter pincode if the pincode input is visible
            try:
                pin_input = page.locator("input[placeholder*='PIN'], input[placeholder*='pin'], #pincode-input, input[name='pincode']").first
                if pin_input.is_visible(timeout=5000):
                    print(f"[BROWSER] Entering pincode {PINCODE}...")
                    pin_input.fill(PINCODE)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(3000)
                else:
                    print("[BROWSER] No pincode input found, checking page as-is...")
            except PlaywrightTimeout:
                print("[BROWSER] Pincode input not found, proceeding...")

            # Step 3: Read the page content
            page_text = page.inner_text("body").lower()

            # Step 4: Detect stock status
            out_signals = [
                "out of stock",
                "notify me",
                "currently unavailable",
                "sold out",
                "not available",
            ]
            in_stock_signals = [
                "add to cart",
                "buy now",
                "add to bag",
            ]

            is_out = any(sig in page_text for sig in out_signals)
            is_in  = any(sig in page_text for sig in in_stock_signals)
            in_stock = is_in and not is_out

            print(f"[BROWSER] Out-of-stock signals: {[s for s in out_signals if s in page_text]}")
            print(f"[BROWSER] In-stock signals    : {[s for s in in_stock_signals if s in page_text]}")

            # Step 5: Try to extract price
            price = "check site"
            price_match = re.search(r'₹\s*([\d,]+)', page.inner_text("body"))
            if price_match:
                price = f"₹{price_match.group(1)}"

            browser.close()
            return {"in_stock": in_stock, "price": price, "error": None}

        except Exception as e:
            browser.close()
            return {"in_stock": False, "price": "N/A", "error": str(e)}


def send_email(price: str):
    """Send a formatted HTML email via Gmail SMTP."""
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
          Sent by your JioMart Stock Notifier (GitHub Actions).
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
        print(f"[ERROR] {result['error']}")

    status = "✅ IN STOCK" if result["in_stock"] else "❌ OUT OF STOCK"
    print(f"[INFO] Status: {status} | Price: {result['price']}")

    if result["in_stock"]:
        print("[INFO] Sending email notification...")
        send_email(result["price"])
    else:
        print("[INFO] Not in stock. No email sent.")


if __name__ == "__main__":
    main()
