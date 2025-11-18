import os
import requests
import time

# -----------------------------
# CONFIG
# -----------------------------
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
MAILERLITE_API_KEY = os.environ.get("MAILERLITE_API_KEY")
MAILERLITE_SUBSCRIBER_EMAIL = os.environ.get("MAILERLITE_SUBSCRIBER_EMAIL")

MODEL = "gpt-4.1-mini"

# -----------------------------
# RETRY LOGIC FOR OPENAI CALL
# -----------------------------
def call_openai_with_retry(payload, headers, retries=3):
    for attempt in range(retries):
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            json=payload,
            headers=headers
        )

        if response.status_code == 429:
            # Rate limit — wait and retry
            wait_time = 3 * (attempt + 1)
            print(f"[OpenAI] 429 rate limit — retrying in {wait_time}s...")
            time.sleep(wait_time)
            continue

        try:
            response.raise_for_status()
        except:
            print("[OpenAI] API error:", response.text)
            raise

        return response.json()

    # All retries failed
    raise Exception("OpenAI API failed after multiple retries.")


# -----------------------------
# GET LIVE GOLD/SILVER PRICES
# -----------------------------
def get_live_prices():
    try:
        gold_resp = requests.get("https://api.metals.live/v1/spot/gold", timeout=10)
        silver_resp = requests.get("https://api.metals.live/v1/spot/silver", timeout=10)

        gold_resp.raise_for_status()
        silver_resp.raise_for_status()

        gold_data = gold_resp.json()
        silver_data = silver_resp.json()

        gold_price = gold_data[0].get("price")
        silver_price = silver_data[0].get("price")

        return {
            "Gold (XAU)": gold_price,
            "Silver (XAG)": silver_price
        }

    except Exception as e:
        print("Price fetch error:", e)
        return {"error": str(e)}



# -----------------------------
# GENERATE DAILY INSIGHT
# -----------------------------
def generate_insight(live_prices):

    # Prepare system prompt
    system_prompt = """
    Készíts magyar nyelvű, rövid, közérthető elemzést az arany és ezüst piacról.
    A stílus legyen profi, de könnyen emészthető.
    Használd fel az árfolyam-adatokat, ha rendelkezésre állnak.
    """

    # Build message for OpenAI
    price_text = ""
    if live_prices and "error" not in live_prices:
        price_text = '\n'.join(f"{k}: {v}" for k, v in live_prices.items() if k != "raw")

    user_message = (
        f"Itt vannak a friss árfolyamok (USD):\n{price_text}\n\n"
        "Kérlek, készíts egy kb. 2 bekezdéses piaci összefoglalót."
    )

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
    }

    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}

    data = call_openai_with_retry(payload, headers)

    try:
        return data["choices"][0]["message"]["content"]
    except:
        return "Hiba történt a szöveg generálásakor."


# -----------------------------
# FORMAT EMAIL (PLAIN TEXT)
# -----------------------------
def format_email_text(insight, prices):
    price_text = ""
    if prices and "error" not in prices:
        price_text = '\n'.join(f"{k}: {v}" for k, v in prices.items() if k != "raw")

    msg = (
        "Arany & Ezüst Piaci Összefoglaló\n\n"
        f"{insight}\n\n"
        "Aktuális árfolyamok (USD):\n"
        f"{price_text}\n\n"
        "Automatizált napi jelentés."
    )
    return msg


# -----------------------------
# SEND EMAIL VIA MAILERLITE
# -----------------------------
def send_email(subject, text_content):

    url = "https://connect.mailerlite.com/api/subscribers"

    payload = {
        "email": MAILERLITE_SUBSCRIBER_EMAIL,
        "fields": {"name": "Subscriber"},
        "status": "active"
    }

    # Ensure the subscriber exists (MailerLite requirement)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MAILERLITE_API_KEY}"
    }

    print("[MailerLite] Adding/updating subscriber...")
    requests.post(url, json=payload, headers=headers)

    # Now send campaign email
    campaign_url = "https://connect.mailerlite.com/api/campaigns"

    campaign_payload = {
        "type": "regular",
        "name": subject,
        "subject": subject,
        "from": "Newsletter Bot",
        "from_email": MAILERLITE_SUBSCRIBER_EMAIL,
        "to": {"type": "subscriber", "email": MAILERLITE_SUBSCRIBER_EMAIL},
        "content": {"plain": text_content},
    }

    print("[MailerLite] Creating campaign...")
    response = requests.post(campaign_url, json=campaign_payload, headers=headers)

    try:
        response.raise_for_status()
        print("[MailerLite] Email sent successfully.")
    except:
        print("[MailerLite] Error sending email:", response.text)


# -----------------------------
# MAIN FUNCTION
# -----------------------------
def main():
    print("Fetching prices...")
    prices = get_live_prices()

    print("Generating insight...")
    insight = generate_insight(prices)

    print("Formatting email...")
    text_email = format_email_text(insight, prices)

    print("Sending email...")
    send_email("Arany & Ezüst Piaci Hírlevél", text_email)

    print("Job done successfully.")


# -----------------------------
# ENTRY POINT
# -----------------------------
if __name__ == "__main__":
    main()

