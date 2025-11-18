import os
import time
import requests
import yfinance as yf

# ============================================================
# CONFIG
# ============================================================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
TO_EMAIL = os.getenv("TO_EMAIL")
FROM_EMAIL = os.getenv("FROM_EMAIL")

MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """
Te egy arany/ezüst piacot elemző szakértő vagy.
Írj egy kb. 3 bekezdéses, közérthető, lényegre törő napi piaci összefoglalót.
Ne ismételd meg a felhasználó által küldött árakat, csak használd fel őket az elemzésben.
"""

# ============================================================
# OPENAI – retry védett hívás
# ============================================================

def call_openai_with_retry(payload, headers, max_retries=5):
    url = "https://api.openai.com/v1/chat/completions"
    for attempt in range(max_retries):
        r = requests.post(url, json=payload, headers=headers)

        if r.status_code == 200:
            return r.json()

        # 429 – rate limit
        if r.status_code == 429:
            wait = 3 * (attempt + 1)
            print(f"[OpenAI] 429 – retry {attempt+1}/{max_retries}, várakozás {wait}s")
            time.sleep(wait)
            continue

        # más hiba → megszakítjuk
        print("[OpenAI ERROR]", r.text)
        r.raise_for_status()

    raise Exception("OpenAI API többszöri próbálkozás után is hibát adott.")

# ============================================================
# ÁRFOLYAMOK (YFINANCE)
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
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    user_msg = "Íme a mai arany/ezüst árak USD-ben:\n"
    if prices:
        user_msg += f"- Arany (XAUUSD): {prices['gold']} USD\n"
        user_msg += f"- Ezüst (XAGUSD): {prices['silver']} USD\n"
    else:
        user_msg += "(Nem sikerült lekérni az árakat.)\n"

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg}
        ]
    }

    data = call_openai_with_retry(payload, headers)
    return data["choices"][0]["message"]["content"]

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
# EMAIL KÜLDÉS SENDGRIDDEL
# ============================================================

def send_email(subject, html):
    url = "https://api.sendgrid.com/v3/mail/send"
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

