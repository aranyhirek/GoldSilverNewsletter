# GoldSilver_News_App.py
# -----------------------------------------
# Replit / Render-ready single-file Python app
# Purpose: generate Hungarian gold/silver market newsletter via OpenAI
#          and send it to MailerLite (Connect API).
# Schedule: designed to be triggered by a cron job (e.g. Render Scheduled Job,
#           GitHub Actions or similar) 2-3 times/week.
#
# WHAT THIS FILE CONTAINS
# - configuration via environment variables
# - optional live price fetching (if METALS_API_KEY provided)
# - OpenAI ChatCompletion-based newsletter generation (Hungarian)
# - MailerLite Connect API campaign creation + content upload + send-to-group
# - basic retry/backoff, logging, and safe-fail behavior
#
# IMPORTANT: before running, set the following environment variables in your host
# environment (Render secrets / Replit Secrets / GitHub Actions secrets):
#
# Required:
#   OPENAI_API_KEY            -> OpenAI API secret key
#   MAILERLITE_API_KEY        -> MailerLite Connect API token
#   MAILERLITE_GROUP_ID       -> (optional) MailerLite group ID to send to
#                                If not provided, set MAILERLITE_SUBSCRIBER_EMAIL
#   MAILERLITE_SUBSCRIBER_EMAIL -> (fallback) a single recipient email for testing
#   SENDER_EMAIL              -> sender email configured in MailerLite (e.g. noreply@yourdomain.com)
#   SENDER_NAME               -> visible sender name (e.g. "AranyHír")
#
# Optional:
#   MODEL                    -> OpenAI model (default: gpt-4o-mini)
#   METALS_API_KEY           -> (optional) API key for a metals price provider
#   METALS_API_URL           -> (optional) price API base url
#   DEBUG                    -> if set, will print more logs
#
# RENDER SCHEDULE EXAMPLE (Render UI):
# - Command: `python3 GoldSilver_News_App.py`
# - Schedule: cron expression (e.g. for Mon/Wed/Fri 09:00 UTC -> `0 9 * * 1,3,5`)
#
# -------------------------
# Quick start:
# 1) Save this file in your project.
# 2) Add the required environment variables to Render / Replit secrets.
# 3) Create a Scheduled Job (cron) to run this script on the days you want.
# 4) Test immediately by running once locally or via Render.
#
# NOTES:
# - This script attempts to be conservative: if MailerLite group ID is provided
#   it will create a campaign and send to that group; otherwise it will send
#   a single test email to MAILERLITE_SUBSCRIBER_EMAIL.
# - Double-check MailerLite sender settings (verified domain / sender email)
#   to avoid delivery problems.
#
# -------------------------

import os
import time
import json
import logging
from typing import Optional

import requests

# Basic logging
DEBUG = os.getenv('DEBUG')
logging.basicConfig(level=logging.DEBUG if DEBUG else logging.INFO)
log = logging.getLogger('gold_silver_news')

# Environment variables / config
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
MAILERLITE_API_KEY = os.getenv('MAILERLITE_API_KEY')
MAILERLITE_GROUP_ID = os.getenv('MAILERLITE_GROUP_ID')
MAILERLITE_SUBSCRIBER_EMAIL = os.getenv('MAILERLITE_SUBSCRIBER_EMAIL')
SENDER_EMAIL = os.getenv('SENDER_EMAIL') or 'noreply@example.com'
SENDER_NAME = os.getenv('SENDER_NAME') or 'AranyHír'
MODEL = os.getenv('MODEL') or 'gpt-4o-mini'
METALS_API_KEY = os.getenv('METALS_API_KEY')
METALS_API_URL = os.getenv('METALS_API_URL') or 'https://metals-api.com/api/latest'

# MailerLite Connect base
MAILERLITE_BASE = 'https://connect.mailerlite.com/api'

# Simple retry decorator
def retry(max_attempts=3, backoff_sec=1.5):
    def deco(f):
        def wrapper(*args, **kwargs):
            attempt = 0
            while True:
                try:
                    return f(*args, **kwargs)
                except Exception as e:
                    attempt += 1
                    log.warning('Attempt %s/%s failed: %s', attempt, max_attempts, e)
                    if attempt >= max_attempts:
                        log.error('Max attempts reached. Raising.')
                        raise
                    time.sleep(backoff_sec * attempt)
        return wrapper
    return deco


@retry(max_attempts=3)
def fetch_live_prices() -> Optional[dict]:
    """Optional: fetch spot prices for XAU (gold) and XAG (silver).
    This uses METALS_API_URL & METALS_API_KEY if provided. The exact provider
    format may differ; code attempts a common JSON structure.
    If METALS_API_KEY not set, returns None.
    """
    if not METALS_API_KEY:
        log.info('No METALS_API_KEY provided — skipping live price fetch.')
        return None
    params = {'access_key': METALS_API_KEY, 'symbols': 'XAU,XAG', 'base': 'USD'}
    try:
        r = requests.get(METALS_API_URL, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        # expected structure may vary by provider
        if 'rates' in data:
            rates = data['rates']
            return {'gold_usd': rates.get('XAU'), 'silver_usd': rates.get('XAG'), 'raw': data}
        # fallback attempts
        return {'raw': data}
    except Exception as e:
        log.warning('Live price fetch failed: %s', e)
        return None


@retry(max_attempts=3)
def generate_newsletter_html(live_prices: Optional[dict] = None) -> str:
    """Call OpenAI Chat Completions to generate a Hungarian newsletter (HTML).
    The model is instructed to produce an HTML fragment suitable for embedding
    into an email body.
    """
    if not OPENAI_API_KEY:
        raise RuntimeError('OPENAI_API_KEY not set')

    system_prompt = (
        'You are a concise Hungarian market analyst specialized in precious metals '
        '(gold and silver). Produce a short, professional newsletter in Hungarian. '
        'Include: headline, 2–4 bullet key points, a short outlook (1 paragraph), '
        'and optionally a short note about risks. Output should be valid HTML fragment '
        'suitable for an email body — use <h1>, <p>, <ul>/<li>, and keep it under 600 words.'
    )

    # If we have live prices, give them to the model as context and ask to mention them
    user_msg = 'Kérlek készíts napi arany/ezüst összefoglalót magyarul.'
if live_prices:
    # include numeric prices if available
    price_text = '\n'.join(f"{k}: {v}" for k, v in live_prices.items() if k != 'raw')
    user_msg += (
        f"\nLive árfolyam adatok (USD):\n{price_text}\n"
        "Kérlek, használd ezeket az értékeket, és tüntesd fel, hogy honnan származnak."
    )
    payload = {
        'model': MODEL,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_msg}
        ],
        'max_tokens': 900
    }

    headers = {
        'Authorization': f'Bearer {OPENAI_API_KEY}',
        'Content-Type': 'application/json'
    }
    resp = requests.post('https://api.openai.com/v1/chat/completions', headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    # Best-effort parsing
    content = None
    try:
        content = data['choices'][0]['message']['content']
    except Exception:
        # Older responses might be in different shape — fallback to string
        content = json.dumps(data)

    # If the model returned plain text, wrap it conservatively into HTML
    if '<' not in content[:20]:
        # naive wrapping
        content = '<div>' + content.replace('\n\n', '</p><p>').replace('\n', '<br/>') + '</div>'

    # Add footer
    footer = f"<hr/><p style=\"font-size:12px;color:#666;\">Ezt a hírlevelet automatizált rendszer küldte — Arany/Ezüst hírek. \n</p>"
    html = f"<div><h1>Arany & Ezüst napi összefoglaló</h1>{content}{footer}</div>"
    return html


@retry(max_attempts=3)
def create_mailerlite_campaign(subject: str, html: str) -> str:
    """Create a campaign in MailerLite Connect API and upload content.
    Returns campaign_id (string)."""
    if not MAILERLITE_API_KEY:
        raise RuntimeError('MAILERLITE_API_KEY not set')

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {MAILERLITE_API_KEY}'
    }

    # 1) create campaign
    body = {
        'subject': subject,
        'from': {'email': SENDER_EMAIL, 'name': SENDER_NAME},
        'type': 'regular'
    }
    r = requests.post(f'{MAILERLITE_BASE}/campaigns', headers=headers, json=body, timeout=30)
    r.raise_for_status()
    camp = r.json()
    campaign_id = camp.get('data', {}).get('id') or camp.get('id')
    if not campaign_id:
        raise RuntimeError('Could not obtain campaign ID from MailerLite response: %s' % camp)

    log.info('Created campaign %s', campaign_id)

    # 2) upload content — many providers use /campaigns/{id}/content or /content endpoints;
    #    try common patterns: first try /campaigns/{id}/content (as in classic API) then fall back
    try:
        # try Connect-style content upload
        r2 = requests.put(f'{MAILERLITE_BASE}/campaigns/{campaign_id}/content', headers={'Authorization': f'Bearer {MAILERLITE_API_KEY}', 'Content-Type': 'text/html'}, data=html.encode('utf-8'), timeout=30)
        if r2.status_code not in (200, 201, 204):
            r2.raise_for_status()
    except Exception as e:
        log.warning('Primary content upload failed: %s — trying alternative endpoint', e)
        # fallback to classic v2 content endpoint
        r3 = requests.put(f'https://api.mailerlite.com/api/v2/campaigns/{campaign_id}/content', headers={'Authorization': f'Bearer {MAILERLITE_API_KEY}', 'Content-Type': 'text/html'}, data=html.encode('utf-8'), timeout=30)
        r3.raise_for_status()

    log.info('Uploaded campaign content')
    return str(campaign_id)


@retry(max_attempts=3)
def send_campaign_to_group(campaign_id: str, group_id: Optional[str] = None, single_email: Optional[str] = None) -> dict:
    """Send campaign to a group or a single email (for testing).
    Returns response JSON.
    """
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {MAILERLITE_API_KEY}'
    }
    if group_id:
        body = {'groups': [int(group_id)] if str(group_id).isdigit() else [group_id]}
        r = requests.post(f'{MAILERLITE_BASE}/campaigns/{campaign_id}/actions/send', headers=headers, json=body, timeout=30)
        r.raise_for_status()
        return r.json()
    elif single_email:
        # If only an email is provided, add subscriber to a temporary group (or upsert and send)
        # Simpler approach: create a one-recipient campaign action (some APIs allow recipients in body)
        body = {'emails': [single_email]}
        r = requests.post(f'{MAILERLITE_BASE}/campaigns/{campaign_id}/actions/send', headers=headers, json=body, timeout=30)
        # If the Connect endpoint doesn't accept 'emails', the request may fail — we catch and raise
        r.raise_for_status()
        return r.json()
    else:
        raise RuntimeError('Neither group_id nor single_email provided for send')


def main():
    log.info('Starting Gold/Silver newsletter job')

    # fetch live prices if possible
    live_prices = None
    try:
        live_prices = fetch_live_prices()
    except Exception as e:
        log.warning('Price fetch failed: %s', e)

    # generate content
    try:
        html = generate_newsletter_html(live_prices=live_prices)
    except Exception as e:
        log.error('OpenAI generation failed: %s', e)
        return

    subject = 'Arany & Ezüst heti összefoglaló'

    # create campaign
    try:
        camp_id = create_mailerlite_campaign(subject, html)
    except Exception as e:
        log.error('Failed to create campaign: %s', e)
        return

    # send
    try:
        if MAILERLITE_GROUP_ID:
            resp = send_campaign_to_group(camp_id, group_id=MAILERLITE_GROUP_ID)
            log.info('Send response: %s', resp)
        elif MAILERLITE_SUBSCRIBER_EMAIL:
            resp = send_campaign_to_group(camp_id, single_email=MAILERLITE_SUBSCRIBER_EMAIL)
            log.info('Send response (single): %s', resp)
        else:
            log.error('No recipient configured: set MAILERLITE_GROUP_ID or MAILERLITE_SUBSCRIBER_EMAIL')
            return
    except Exception as e:
        log.error('Failed to send campaign: %s', e)
        return

    log.info('Job finished successfully')


if __name__ == '__main__':

    main()

