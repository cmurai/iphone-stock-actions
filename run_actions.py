"""One check per Actions run; optional Slack notification and persisted state."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

from iphone_stock import CheckError, build_url, fetch, parse_rows

STATE = Path('.stock-state/state.json')


def notify(webhook, rows):
    target = urllib.parse.urlsplit(webhook)
    if (target.scheme != 'https' or target.hostname not in
            ('hooks.slack.com', 'hooks.slack-gov.com') or target.username or
            target.password or target.port not in (None, 443) or
            not target.path.startswith('/services/')):
        raise CheckError('SLACK_WEBHOOK_URL must be a Slack incoming webhook URL.')
    text = 'Apple pickup availability detected:\n' + '\n'.join(
        f"{r['store']} ({r['store_id']}) — {r['product']} [{r['part']}] — {r['message']}"
        for r in rows)
    text += '\nConfirm the pickup date and order at https://www.apple.com/shop/buy-iphone/iphone-duo . No stock is reserved.'
    # Plain text prevents product/store data from becoming Slack mentions.
    request = urllib.request.Request(webhook, data=json.dumps({
        'text': text, 'mrkdwn': False, 'unfurl_links': False,
        'unfurl_media': False}).encode(), headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.read().strip() != b'ok':
                raise CheckError('Slack did not acknowledge the alert; state was not advanced.')
    except (urllib.error.URLError, OSError) as exc:
        # Never print exceptions containing a secret webhook URL.
        raise CheckError('Slack delivery failed; state was not advanced. Check the webhook secret and retry.') from None


def run():
    args = argparse.Namespace(
        request_url=os.environ.get('APPLE_REQUEST_URL') or None,
        zip=os.environ.get('APPLE_ZIP') or None,
        part=[p.strip() for p in os.environ.get('APPLE_PARTS', '').split(',') if p.strip()] or None)
    stores = {s.strip() for s in os.environ.get('APPLE_STORES', '').split(',') if s.strip()}
    webhook = os.environ.get('SLACK_WEBHOOK_URL', '').strip()
    try:
        url, parts = build_url(args)
        fingerprint = hashlib.sha256(json.dumps([url, sorted(stores), webhook]).encode()).hexdigest()
        previous = {}
        if STATE.exists():
            saved = json.loads(STATE.read_text())
            if not isinstance(saved, dict) or not isinstance(saved.get('states'), dict):
                raise CheckError('Invalid state file; remove the Actions state cache and retry.')
            if saved.get('config') == fingerprint:
                previous = saved['states']
        rows = parse_rows(fetch(url), parts, stores)
        next_states = dict(previous)
        alerts = []
        for row in rows:
            key = row['store_id'] + ':' + row['part']
            print(f"{row['state']} | {row['store']} ({row['store_id']}) | {row['product']} | {row['message']}")
            if row['state'] == 'AVAILABLE' and previous.get(key) != 'AVAILABLE':
                alerts.append(row)
            if row['state'] != 'UNKNOWN':
                next_states[key] = row['state']
        if alerts:
            if webhook:
                notify(webhook, alerts)
                print(f'Slack accepted one alert covering {len(alerts)} pickup options.')
            else:
                print(f'{len(alerts)} new pickup options; Slack is not configured.')
        STATE.parent.mkdir(parents=True, exist_ok=True)
        temporary = STATE.with_suffix('.tmp')
        temporary.write_text(json.dumps({'config': fingerprint, 'states': next_states}, indent=2))
        temporary.replace(STATE)
        return 0
    except (CheckError, ValueError, OSError) as exc:
        # Log only known safe error messages. Never echo input URLs.
        message = str(exc) if isinstance(exc, CheckError) else 'Invalid configuration or unreadable state file.'
        print(f'ERROR: {message}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(run())
