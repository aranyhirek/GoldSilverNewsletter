import os
import requests

# ===== Environment Variables =====
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
MAILERLITE_API_KEY = os.environ.get("MAILERLITE_API_KEY")
MAILERLITE_GROUP_ID = os.environ.get("MAILERLITE_GROUP_ID")
MAILERLITE_SUBSCRIBER_EMAIL = os.environ.get("MAILERLITE_SUBSCRIBER_EMAIL", "")
SENDER_NAME = os.environ.get("SENDER_NAME", "AranyHír")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "noreply@example.com")

# ===== Example live prices (replace with API if needed) =====
live_prices = {
    "Gold": "1,950 USD/oz",
    "Silver": "24 USD/oz",
    "raw": "ignore"
}

# ===== Build user message =====
if live_prices:
    price_text = '\n'.join(f"{k}: {v}" for k, v in live_prices.items() if k != 'raw')
    user_msg = (
        f"Live árfolyam adatok (USD):\n{price_text}\n"
        "Kérlek, használd ezeket az értékeket, és tüntesd fel, hogy honnan származnak."
    )
else:
    user_msg = "Nincsenek elérhető árfolyam adatok."

# ===== OpenAI prompt =====
system_prompt = (
    "Te vagy egy pénzügyi elemző, aki magyar nyelvű arany/ezüst piaci összefoglalót készít."
)

prompt = f"""
Kérlek, írj rövid magyar nyelvű hírlevelet a következő árfolyamok alapján:

{user_msg}

Formázd szöveges, könnyen olvasható módon.
"""

# ===== Call OpenAI API =====
openai_url = "https://api.openai.com/v1/chat/completions"
headers = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json"
}
payload = {
    "model": "gpt-3.5-turbo",
    "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ],
    "temperature": 0.7
}

response = requests.post(openai_url, headers=headers, json=payload)
response.raise_for_status()
data = response.json()
generated_content = data['choices'][0]['message']['content']

# ===== Build HTML email =====
html_email = f"""
<div>
<h1>Arany & Ezüst napi összefoglaló</h1>
<p>{generated_content}</p>
<hr/>
<p style="font-size:12px;color:#666;">
Ezt a hírlevelet automatizált rendszer küldte — Arany/Ezüst hírek.
</p>
</div>
"""

# ===== Send via MailerLite =====
mailer_url = f"https://api.mailerlite.com/api/v2/groups/{MAILERLITE_GROUP_ID}/subscribers"

# Prepare subscriber payload
subscriber_payload = {
    "email": MAILERLITE_SUBSCRIBER_EMAIL,
    "fields": {
        "name": SENDER_NAME
    },
    "resubscribe": True
}

# Add subscriber (if not exists)
requests.post(
    mailer_url,
    headers={"X-MailerLite-ApiKey": MAILERLITE_API_KEY, "Content-Type": "application/json"},
    json=subscriber_payload
)

# Send campaign
campaign_payload = {
    "subject": "Heti Arany/Ezüst Hírlevél",
    "from": {"email": SENDER_EMAIL, "name": SENDER_NAME},
    "html": html_email,
    "groups": [MAILERLITE_GROUP_ID]
}

campaign_url = "https://api.mailerlite.com/api/v2/campaigns"
campaign_response = requests.post(
    campaign_url,
    headers={"X-MailerLite-ApiKey": MAILERLITE_API_KEY, "Content-Type": "application/json"},
    json=campaign_payload
)
campaign_response.raise_for_status()

print("Hírlevél sikeresen elküldve!")
