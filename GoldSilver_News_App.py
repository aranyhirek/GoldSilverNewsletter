import os
import time
import requests
import yfinance as yf

# ============================================================
# CONFIG
# ============================================================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")  # vagy MailerLite kulcs
TO_EMAIL = os.getenv("TO_EMAIL")
FROM_EMAIL = os.getenv("FROM_EMAIL")

MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """
Te egy arany/ezüst piacot elemző szakértő vagy.
Írj egy kb. 3 bekezdéses, közérthető, lényegre törő napi piaci összefoglalót.
Ne ismételd meg a felhasználó által küldött árakat, csak használd fel őket az elemzésben.
"""

# ============================================================
# OPENAI – modern hívás 429-re retry
# ============================================================

def call_openai_with_retry(messages, max_retries=5):
    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "input": messages
    }

    wait_times = [5, 15, 30, 60, 120]

    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            if response.status_code == 429:
                wait = wait_times[attempt]
                print(f"[OpenAI] 429 – retry {attempt+1}/{max_retries}, várakozás {wait}s")
                time.sleep(wait)
                continue
            response.raise_for_status()
            data = response.json()
            return data["output_text"] if "output_text" in data else data
        except requests.exceptions.RequestException as e:
            wait = wait_times[attempt]
            print(f"[OpenAI] Hiba: {e} – újrapróbálás {wait}s")
            time.sleep(wait)
    raise Exception("OpenAI API többszöri próbálkozás után is hibát adott.")

# ============================================================
# YFinance árfolyam
# ============================================================

def get_live_prices():
    try:
        gold = yf.Ticker("GC=F").history(period="1d")
        silver = yf.Ticker("SI=F").history(period="1d")

        if gold.empty or silver.empty:
            raise ValueError("Üres YF adat – próbáld később újra.")

        gold_price = round(gold["Close"].iloc[-1], 2)
        silver_price = round(silver["Close"].iloc[-1], 2)

        return {
            "Gold (XAU)": gold_price,
            "Silver (XAG)": silver_price
        }

    except Exception as e:
        print("Price fetch error:", e)
        return {"error": str(e)}

# ============================================================
# INSIGHT GENERÁLÁS
# ============================================================

def generate_insight(prices):
    user_msg = "Íme a mai arany/ezüst árak USD-ben:\n"
    if prices and "error" not in prices:
        user_msg += f"- Arany (XAU): {prices['Gold (XAU)']} USD\n"
        user_msg += f"- Ezüst (XAG): {prices['Silver (XAG)']} USD\n"
    else:
        user_msg += "(Nem sikerült lekérni az árakat.)\n"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg}
    ]

    return call_openai_with_retry(messages)

# ============================================================
# HTML GENERÁLÁS
# ============================================================

def generate_html(content):
    footer = """
    <hr>
    <p style="font-size:12px;color:#555;">
        Ezt az e-mailt egy automatizált rendszer küldte – Arany/Ezüst Piaci Összefoglaló.
    </p>
    """
    html = f"""
    <div style="font-family:Arial; padding:20px;">
        <h1>Arany & Ezüst Piaci Összefoglaló</h1>
        <div style="font-size:16px; line-height:1.6;">
            {content}
        </div>
        {footer}
    </div>
    """
    return html

# ============================================================
# EMAIL KÜLDÉS SENDGRID / MailerLite
# ============================================================

def send_email(subject, html):
    url = "https://api.sendgrid.com/v3/mail/send"  # vagy MailerLite endpoint
    headers = {
        "Authorization": f"Bearer {SENDGRID_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "personalizations": [{"to": [{"email": TO_EMAIL}]}],
        "from": {"email": FROM_EMAIL},
        "subject": subject,
        "content": [{"type": "text/html", "value": html}]
    }
    r = requests.post(url, json=payload, headers=headers)
    if r.status_code >= 300:
        print("Email error:", r.text)
    else:
        print("Email sent successfully.")

# ============================================================
# MAIN
# ============================================================

def main():
    print("=== Gold/Silver Daily Job started ===")
    prices = get_live_prices()
    insight = generate_insight(prices)
    html = generate_html(insight)
    send_email("Arany & Ezüst napi összefoglaló", html)
    print("=== Job finished ===")

if __name__ == "__main__":
    main()
