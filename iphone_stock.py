#!/usr/bin/env python3
"""Check nearby Apple Store pickup availability (Python 3.9+, no dependencies).

SETUP (on a Mac, Windows PC, or Linux computer)
1. Open https://www.apple.com/shop/buy-iphone/iphone-duo in a desktop browser.
2. Select your exact color, storage, carrier, and payment option.
3. Open Developer Tools > Network, then check pickup availability with your ZIP.
4. Filter Network requests for 'fulfillment-messages'. Copy the Request URL
   for the successful request (not 'Copy as cURL', cookies, or account tokens).
5. Run once, putting that URL in quotes:
     python3 iphone_stock.py --request-url 'PASTE_APPLE_REQUEST_URL'
   Or check every five minutes while this terminal/computer stays running:
     python3 iphone_stock.py --request-url 'PASTE_APPLE_REQUEST_URL' --watch
   Override the location: add --zip 94086. Restrict stores: --store R001
   (repeat --store for more). Store IDs appear in the output.

Alternatively, copy the exact parts.0 value from that request and run:
  python3 iphone_stock.py --zip 94086 --part 'YOUR_APPLE_PART_NUMBER' --watch
Repeat --part to check multiple configurations in one request. Part numbers
are region/configuration-specific; do not use the hardware model (Axxxx).
--part mode uses the US store; --request-url preserves the regional endpoint.

Alerts are console messages and a terminal bell (if your terminal supports it),
not phone push notifications. Nothing is purchased or reserved. A future pickup
date is not stock available today: read the displayed pickup message.

LIMITATIONS
Uses Apple's undocumented storefront endpoint, which can change or block
automated requests. HTTP 403/429 stop the script; there is no challenge bypass.
Missing/unrecognized data is UNKNOWN, never assumed out of stock. Store coverage
is whatever Apple returns for your location, not a guaranteed geographic radius.
Live endpoint access could not be verified in the authoring environment; parsing
and failures were tested with synthetic fixtures. Initial setup needs a desktop
browser; this is not an iOS background app. Stop with Ctrl-C.

Reference behavior: https://orionchime.com/iphone-inventory-checker/
"""

import argparse
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


class CheckError(Exception):
    pass


class StopChecking(CheckError):
    pass


def clean(value):
    return ' '.join(html.unescape(re.sub(r'<[^>]*>', '', str(value or ''))).split())


def build_url(args):
    base = args.request_url or 'https://www.apple.com/shop/fulfillment-messages'
    parsed = urllib.parse.urlsplit(base)
    if (parsed.scheme != 'https' or parsed.hostname not in
            ('www.apple.com', 'www.apple.com.cn') or parsed.username or
            parsed.password or parsed.port not in (None, 443) or
            not re.fullmatch(r'/(?:[a-z]{2}/)?shop/fulfillment-messages', parsed.path)):
        raise CheckError('Use an HTTPS Apple storefront fulfillment-messages URL.')
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    if not args.request_url:
        query.update({'pl': 'true', 'mts.0': 'regular', 'searchNearby': 'true'})
    if args.zip:
        query['location'] = args.zip
        query.pop('store', None)
    if args.part:
        query = {k: v for k, v in query.items() if not k.startswith('parts.')}
        query.update({f'parts.{i}': p for i, p in enumerate(args.part)})
    parts = [v for k, v in query.items() if re.fullmatch(r'parts\.\d+', k) and v]
    if not parts or not (query.get('location') or query.get('store')):
        raise CheckError('Provide a request URL containing parts and location, or --zip and --part.')
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path,
                                   urllib.parse.urlencode(query), '')), parts


def fetch(url):
    request = urllib.request.Request(url, headers={
        'Accept': 'application/json', 'User-Agent': 'ApplePickupChecker/1.0'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 429):
            raise StopChecking(f'Apple returned HTTP {exc.code}; stopped. Check manually in your browser.') from exc
        raise CheckError(f'Apple returned HTTP {exc.code}; availability is unknown.') from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise CheckError(f'Cannot read Apple inventory ({type(exc).__name__}); availability is unknown.') from exc


def parse_rows(payload, parts, stores):
    try:
        status = payload.get('head', {}).get('status')
        if status is not None and str(status) != '200':
            raise CheckError(f'Apple response status {status}; availability is unknown.')
        entries = payload['body']['content']['pickupMessage']['stores']
        if not isinstance(entries, list) or not entries:
            raise CheckError('No store results returned; availability is unknown.')
        rows = []
        for store in entries:
            store_id = str(store['storeNumber'])
            if stores and store_id not in stores:
                continue
            for part in parts:
                info = store.get('partsAvailability', {}).get(part, {})
                raw = str(info.get('pickupDisplay', '')).lower()
                state = {'available': 'AVAILABLE', 'unavailable': 'UNAVAILABLE'}.get(raw, 'UNKNOWN')
                details = info.get('messageTypes', {}).get('regular', {})
                name = clean(details.get('storePickupProductTitle')) or part
                message = clean(info.get('pickupSearchQuote') or info.get('pickupQuote'))
                rows.append({'store_id': store_id, 'store': clean(store.get('storeName')),
                             'part': part, 'product': name, 'state': state,
                             'message': message or 'No pickup date/message provided'})
        if not rows:
            raise CheckError('Selected stores were not returned; availability is unknown.')
        return rows
    except (KeyError, TypeError, AttributeError) as exc:
        raise CheckError('Unexpected Apple response format; availability is unknown.') from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--request-url', help='Apple pickup request URL copied from browser Network tab')
    parser.add_argument('--zip', help='ZIP/postal code (US unless using a regional request URL)')
    parser.add_argument('--part', action='append', help='Exact Apple part number; repeat for multiple variants')
    parser.add_argument('--store', action='append', default=[], help='Store ID to include; repeat as needed')
    parser.add_argument('--watch', action='store_true', help='Keep checking until Ctrl-C')
    parser.add_argument('--interval', type=int, default=300, help='Seconds between checks; minimum 300')
    args = parser.parse_args()
    if args.interval < 300:
        parser.error('--interval must be at least 300 seconds')
    try:
        url, parts = build_url(args)
    except (CheckError, ValueError) as exc:
        parser.error(str(exc))
    previous = {}
    failures = 0
    while True:
        try:
            rows = parse_rows(fetch(url), parts, set(args.store))
            print('\n' + dt.datetime.now().astimezone().isoformat(timespec='seconds'), flush=True)
            for row in rows:
                print(f"{row['state']:11} | {row['store']} ({row['store_id']}) | "
                      f"{row['product']} [{row['part']}] | {row['message']}", flush=True)
                key = (row['store_id'], row['part'])
                if row['state'] == 'AVAILABLE' and previous.get(key) != 'AVAILABLE':
                    print('\aALERT: Pickup offered. Confirm the date and complete your order at Apple.', flush=True)
                # Unknown data must not reset a previously confirmed availability state.
                if row['state'] != 'UNKNOWN':
                    previous[key] = row['state']
            failures = 0
        except StopChecking as exc:
            print(f'ERROR: {exc}', file=sys.stderr, flush=True)
            return 2
        except CheckError as exc:
            print(f'ERROR: {exc}', file=sys.stderr, flush=True)
            if not args.watch:
                return 2
            failures += 1
        if not args.watch:
            return 0
        time.sleep(max(args.interval, min(3600, 300 * 2 ** min(failures, 4))))


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\nStopped.')
        sys.exit(130)
