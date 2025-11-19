import os
import json
import requests
import datetime
import time
import hashlib
from zoneinfo import ZoneInfo

# ===================== CONFIG =====================
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY")
MAILERLITE_API_KEY  = os.getenv("MAILERLITE_API_KEY")
NEWSAPI_KEY         = os.getenv("NEWSAPI_KEY")          # https://newsapi.org (ingyenes is elég)
MAILERLITE_GROUP_ID = os.getenv("MAILERLITE_GROUP_ID", "123456789")  # ide írd a feliratkozói csoport ID-jét
TEST_MODE           = True        # True = csak neked küldi (info@solinvictus.hu), False = teljes csoportnak
FROM_NAME           = "Sol Invictus – Arany & Ezüst Hírek"
FROM_EMAIL          = "info@solinvictus.hu"
MODEL               = "gpt-4o-mini"
LAST_SENT_FILE      = "last_sent_news.json"   # duplikáció védelem
TZ_BUDAPEST         = ZoneInfo("Europe/Budapest")

# ===================== HÍRGYŰJTÉS – GOOGLE NEWS RSS (SOHA TÖBBÉ NEM LESZ 0 HÍR) =====================
def get_fresh_news():
    news = []
    # Google News RSS – mindig friss, mindig működik
    google_rss_urls = [
        "https://news.google.com/rss/search?q=arany+OR+ez%C3%BCst+OR+gold+OR+silver+OR+XAU+OR+XAG+when:4d&hl=hu&gl=HU&ceid=HU:hu",
        "https://news.google.com/rss/search?q=gold+OR+silver+OR+%22precious+metals%22+when:4d&hl=en-US&gl=US&ceid=US:en",
    ]

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    try:
        import feedparser
        for url in google_rss_urls:
            feed = feedparser.parse(url, request_headers=headers)
            for entry in feed.entries[:30]:
                title = entry.title.lower()
                summary = getattr(entry, "summary", "").lower()
                text = title + " " + summary
                if any(kw in text for kw in ["gold", "arany", "silver", "ezüst", "xau", "xag", "bullion", "drágametall"]):
                    news.append({
                        "title": entry.title,
                        "description": getattr(entry, "summary", "")[:300],
                        "url": entry.link,
                        "publishedAt": getattr(entry, "published", "")
                    })
    except Exception as e:
        print(f"Hírgyűjtés hiba: {e}")

    # Deduplikáció
    seen = set()
    unique = []
    for n in news:
        if n["title"] not in seen:
            seen.add(n["title"])
            unique.append(n)

    print(f"⚡ Google News-ből talált egyedi releváns hírek: {len(unique)} db")
    for i, n in enumerate(unique[:8], 1):
        print(f"   {i}. {n['title'][:100]}")

    return unique[:20]
# ===================== Duplikáció védelem =====================
def already_sent_today():
    if not os.path.exists(LAST_SENT_FILE):
        return False
    with open(LAST_SENT_FILE, "r") as f:
        data = json.load(f)
        last_date = datetime.datetime.fromisoformat(data["date"]).date()
        today = datetime.datetime.now(TZ_BUDAPEST).date()
        return last_date == today and data.get("sent", False)

def mark_as_sent(news_items):
    news_hash = hashlib.md5("".join([n["title"] for n in news_items]).encode()).hexdigest()
    data = {
        "date": datetime.datetime.now(TZ_BUDAPEST).isoformat(),
        "sent": True,
        "hash": news_hash
    }
    with open(LAST_SENT_FILE, "w") as f:
        json.dump(data, f)

# ===================== OpenAI összefoglaló =====================
def call_openai(messages):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": MODEL, "messages": messages, "temperature": 0.7}
    
    for i in range(5):
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
        if r.status_code == 429:
            time.sleep((i + 1) * 5)
    raise Exception("OpenAI hiba")

def generate_newsletter_content(news, prices):
    news_text = "\n".join([f"- {n['title']} ({n.get('publishedAt', '')[:10]})" for n in news[:12]])
    
    prompt = f"""
    Készíts egy magyar nyelvű, profi pénzügyi hírlevelet arany és ezüst befektetőknek.
    Mai árak: Arany: {prices['gold']:.2f} USD | Ezüst: {prices['silver']:.2f} USD

    Friss hírek az elmúlt 4 napból:
    {news_text}

    Kérlek, írj:
    1. Rövid, figyelemfelkeltő subject line-t (max 60 karakter)
    2. Preheader szöveget (max 100 karakter, amit a subject után látnak mobilon)
    3. 3-5 mondatos bevezetőt
    4. 4-6 legfontosabb hír bullet pointban, magyarul, rövid magyarázattal
    5. Záró mondatot, ami cselekvésre ösztönöz (pl. portfólió áttekintés)

    Formázd úgy, hogy közvetlenül HTML-be illeszthető legyen.
    """
    messages = [
        {"role": "system", "content": "Te egy magyar pénzügyi hírlevél-szerkesztő vagy, aki arany/ezüst témában ír."},
        {"role": "user", "content": prompt}
    ]
    return call_openai(messages)

# ===================== Árak (yfinance) =====================
def get_prices():
    import yfinance as yf
    try:
        gold = yf.Ticker("XAUUSD=X").history(period="2d")["Close"].iloc[-1]
        silver = yf.Ticker("XAGUSD=X").history(period="2d")["Close"].iloc[-1]
        return {"gold": round(gold, 2), "silver": round(silver, 2)}
    except:
        return {"gold": "N/A", "silver": "N/A"}

# ===================== MailerLite Campaign =====================
def create_and_send_campaign(subject, preheader, html_content):
    url = "https://connect.mailerlite.com/api/campaigns"
    headers = {"Authorization": f"Bearer {MAILERLITE_API_KEY}", "Content-Type": "application/json"}

    # Teszt módban csak neked küldi
    payload = {
        "name": f"Arany-Ezüst Hírlevél – {datetime.datetime.now(TZ_BUDAPEST).strftime('%Y-%m-%d')}",
        "subject": subject,
        "emails": [{"subject": subject, "content": html_content}],
        "type": "regular"
    }

    if TEST_MODE:
        payload["groups"] = []  # nincs csoport
        payload["test"] = {"emails": [FROM_EMAIL]}  # csak neked
    else:
        payload["groups"] = [int(MAILERLITE_GROUP_ID)]

    r = requests.post(url, headers=headers, json=payload)
    if r.status_code == 201:
        campaign_id = r.json()["data"]["id"]
        # Küldés indítása
        requests.post(f"https://connect.mailerlite.com/api/campaigns/{campaign_id}/schedule",
                      headers=headers, json={"send_at": "now"})
        print("✅ Kampány létrehozva és elküldve!")
    else:
        print("❌ MailerLite hiba:", r.text)

# ===================== HTML sablon =====================
def build_html(subject, preheader, body, prices):
    today = datetime.datetime.now(TZ_BUDAPEST).strftime("%Y. március %d., %A")
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{subject}</title>
        <meta name="preheader" content="{preheader}">
    </head>
    <body style="margin:0; padding:0; background:#f4f4f4; font-family:Arial, sans-serif;">
        <div style="display:none; font-size:1px; color:#f4f4f4; max-height:0px; overflow:hidden;">
            {preheader}
        </div>
        <table width="100%" bgcolor="#f4f4f4" cellpadding="0" cellspacing="0">
            <tr><td align="center">
                <table width="600" bgcolor="#ffffff" style="margin:20px 0; border-radius:8px; overflow:hidden; box-shadow:0 4px 20px rgba(0,0,0,0.1);">
                    <tr>
                        <td bgcolor="#1a1a1a" style="padding:30px 20px; text-align:center; color:white;">
                            <h1 style="margin:0; font-size:26px;">Sol Invictus</h1>
                            <p style="margin:10px 0 0; font-size:16px; opacity:0.9;">Arany & Ezüst Hírlevél</p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:30px;">
                            <p style="color:#666; font-size:14px;">{today}</p>
                            <h2 style="color:#b8860b; border-bottom:2px solid #b8860b; padding-bottom:10px;">Aktuális árak</h2>
                            <p><strong>Arany (XAU/USD):</strong> {prices['gold']} USD<br>
                               <strong>Ezüst (XAG/USD):</strong> {prices['silver']} USD</p>
                            
                            {body}
                            
                            <hr style="border:0; border-top:1px solid #eee; margin:30px 0;">
                            <p style="font-size:12px; color:#999;">
                                © 2025 Sol Invictus • <a href="*|UNSUBSCRIBE|*" style="color:#999;">Leiratkozás</a>
                            </p>
                        </td>
                    </tr>
                </table>
            </td></tr>
        </table>
    </body>
    </html>
    """

# ===================== MAIN =====================
def main():
    print(f"Arany/Ezüst hírlevél indítása – {datetime.datetime.now(TZ_BUDAPEST).strftime('%Y-%m-%d %H:%M')}")

    if already_sent_today():
        print("Ma már küldtünk hírlevelet → kilépés")
        return

    news = get_fresh_news()
    print(f"Talált hírek száma: {len(news)}")
    if len(news) < 1:   # teszteléshez 1, élesben később 3-4
        print("Nincs elég új hír ma → nem küldünk")
        return

    prices = get_prices()
    content = generate_newsletter_content(news, prices)

    # GPT válasza szétválasztása
    lines = [l.strip() for l in content.split("\n") if l.strip()]
    subject = lines[0].replace("Subject:", "").replace("Tárgy:", "").strip()
    preheader = lines[1].strip() if len(lines) > 1 else "Friss arany és ezüst piaci hírek"
    body = "\n".join(lines[2:])

    html = build_html(subject, preheader, body, prices)
    create_and_send_campaign(subject, preheader, html)
    mark_as_sent(news)


if __name__ == "__main__":
    main()



