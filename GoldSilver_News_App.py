import os
import requests
import json
import time
import datetime
import yfinance as yf

# =====================
# CONFIG
# =====================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MAILERLITE_API_KEY = os.getenv("MAILERLITE_API_KEY")

FROM_EMAIL = "info@solinvictus.hu"
FROM_NAME = "GoldSilver Bot"
TO_EMAIL = "info@solinvictus.hu"

MODEL = "gpt-4o-mini"


# =====================
# OpenAI retry wrapper
# =====================

def call_openai_with_retry(messages, max_retries=5):
    url = "https://api.openai.com/v1/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}",
    }

    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.7
    }

    for attempt in range(1, max_retries + 1):
        response = requests.post(url, headers=headers, json=payload)

        if response.status_code == 429:
            wait = attempt * 5 if attempt < 4 else attempt * 15
            print(f"[OpenAI] 429 – retry {attempt}/{max_retries}, várakozás {wait}s")
            time.sleep(wait)
            continue

        if 200 <= response.status_code < 300:
            data = response.json()
            return data["choices"][0]["message"]["content"]

        print(f"[OpenAI] {response.status_code} hiba: {response.text}")
        time.sleep(3)

    raise Exception("OpenAI API többszöri próbálkozás után is hibát adott.")


# =====================
# Ár adatgyűjtés YFinance
# =====================

def get_prices():
    try:
        gold_data = yf.Ticker("XAUUSD=X").history(period="1d")
        silver_data = yf.Ticker("XAGUSD=X").history(period="1d")

        gold_price = float(gold_data["Close"].iloc[-1]) if not gold_data.empty else "N/A"
        silver_price = float(silver_data["Close"].iloc[-1]) if not silver_data.empty else "N/A"

        return {"gold": gold_price, "silver": silver_price}

    except Exception as e:
        print("Price fetch error:", str(e))
        return {"gold": "N/A", "silver": "N/A"}


# =====================
# Insight generálása OpenAI segítségével (frissített prompt)
# =====================

def generate_insight(prices):
    user_message = (
        f"Az aktuális árak a mai napra:\n"
        f"- Arany (XAUUSD): {prices.get('gold', 'N/A')} USD\n"
        f"- Ezüst (XAGUSD): {prices.get('silver', 'N/A')} USD\n\n"
        "Kérlek, készíts rövid, 3-5 soros piaci elemzést magyarul, "
        "vegyél figyelembe minden releváns nemzetközi hírt és trendet az arany és ezüst piacáról, "
        "és írd úgy, hogy egy üzleti hírlevélben felhasználható legyen."
    )

    messages = [
        {"role": "system", "content": "Te egy pénzügyi szakértő vagy, aki napi összefoglalót készít arany/ezüst árakról és trendekről."},
        {"role": "user", "content": user_message}
    ]

    result = call_openai_with_retry(messages)
    return result


# =====================
# HTML email sablon
# =====================

def build_email_html(prices, insight):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    return f"""
    <html>
    <body style="font-family: Arial; background: #f7f7f7; padding: 20px;">
        <div style="max-width: 600px; margin: auto; background: white; padding: 20px; border-radius: 8px;">
            <h2>Napi Arany/Ezüst Jelentés – {now}</h2>

            <h3>Árak</h3>
            <p><b>Arany (XAUUSD):</b> {prices.get('gold', 'N/A')} USD</p>
            <p><b>Ezüst (XAGUSD):</b> {prices.get('silver', 'N/A')} USD</p>

            <h3>Napi Elemzés</h3>
            <p>{insight}</p>

            <br><br>
            <p style="font-size: 12px; color: #777;">
                Automatikusan generált jelentés a Sol Invictus rendszeréből.
            </p>
        </div>
    </body>
    </html>
    """


# =====================
# MailerLite – email küldés 1 címre
# =====================

def send_email_via_mailerlite(subject, html_content):
    url = "https://connect.mailerlite.com/api/email/send"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MAILERLITE_API_KEY}"
    }

    payload = {
        "from": {
            "email": FROM_EMAIL,
            "name": FROM_NAME
        },
        "to": [
            {"email": TO_EMAIL}
        ],
        "subject": subject,
        "content": html_content
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))

        if 200 <= response.status_code < 300:
            print("✔ Email elküldve MailerLite-tal.")
        else:
            print("❌ Email error:", response.text)

    except Exception as e:
        print("❌ Email sending failed:", str(e))


# =====================
# MAIN
# =====================

def main():
    print("=== Gold/Silver Daily Job started ===")

    prices = get_prices()
    insight = generate_insight(prices)
    email_html = build_email_html(prices, insight)

    send_email_via_mailerlite("Napi Arany/Ezüst jelentés", email_html)

    print("=== Job finished ===")


if __name__ == "__main__":
    main()
