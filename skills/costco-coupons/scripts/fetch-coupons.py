#!/usr/bin/env python3
"""
Fetch current Costco Canada coupon/savings page using the OpenClaw managed browser
CDP endpoint (port 18800). Extracts and parses all current savings offers.

Usage:
  python3 fetch-coupons.py
  python3 fetch-coupons.py --raw      # dump raw innerText only
"""

import json
import sys
import time
import re
import urllib.request
import argparse

DEVTOOLS_URL = "http://127.0.0.1:18800"
COUPONS_URL = "https://www.costco.ca/coupons.html"
WAIT_SECONDS = 6  # time to let JS render after opening tab


def get_tabs():
    with urllib.request.urlopen(f"{DEVTOOLS_URL}/json", timeout=5) as r:
        return json.loads(r.read())


def open_new_tab(url):
    import urllib.parse
    encoded = urllib.parse.quote(url, safe=':/')
    req = urllib.request.Request(f"{DEVTOOLS_URL}/json/new?{encoded}", method="PUT")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def close_tab(target_id):
    try:
        urllib.request.urlopen(f"{DEVTOOLS_URL}/json/close/{target_id}", timeout=5)
    except Exception:
        pass


def cdp_eval(ws_debugger_url, expression, timeout=25):
    """Evaluate JS via CDP WebSocket. Returns (value, error)."""
    try:
        import websocket
    except ImportError:
        return None, "websocket-client not installed. Run: pip3 install websocket-client"

    import threading
    result = {}
    done = threading.Event()
    msg_id = 42

    def on_open(ws):
        ws.send(json.dumps({
            "id": msg_id,
            "method": "Runtime.evaluate",
            "params": {"expression": expression, "returnByValue": True}
        }))

    def on_message(ws, message):
        data = json.loads(message)
        if data.get("id") == msg_id:
            r = data.get("result", {})
            if "exceptionDetails" in r:
                result["error"] = str(r["exceptionDetails"])
            else:
                result["value"] = r.get("result", {}).get("value", "")
            done.set()
            ws.close()

    def on_error(ws, error):
        result["error"] = str(error)
        done.set()

    ws = websocket.WebSocketApp(
        ws_debugger_url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error
    )
    t = threading.Thread(target=ws.run_forever, kwargs={"suppress_origin": True})
    t.daemon = True
    t.start()
    done.wait(timeout)
    return result.get("value"), result.get("error")


def parse_coupons(raw_text):
    """Parse innerText of costco.ca/coupons.html into list of coupon dicts."""
    coupons = []
    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]

    i = 0
    while i < len(lines):
        if not lines[i].startswith("Valid "):
            i += 1
            continue

        valid_str = lines[i]
        i += 1

        # Find SAVE block
        save_idx = None
        for j in range(i, min(i + 5, len(lines))):
            if lines[j] == "SAVE":
                save_idx = j
                break
        if save_idx is None:
            continue

        # Savings amount (e.g. "$20" or "$3.50")
        amt_idx = save_idx + 1
        savings_raw = lines[amt_idx] if amt_idx < len(lines) else ""
        # Sometimes "PER PACK*" follows the amount
        savings_note = ""
        next_idx = amt_idx + 1
        if next_idx < len(lines) and lines[next_idx].startswith("PER "):
            savings_note = lines[next_idx]
            next_idx += 1

        # Product name: everything up to "Item number" or "In-warehouse" or "SAVE"
        name_parts = []
        k = next_idx
        while k < len(lines):
            l = lines[k]
            if l.startswith("Item number") or l.startswith("In-warehouse") or l == "SAVE" or l.startswith("Valid "):
                break
            name_parts.append(l)
            k += 1
        name = " ".join(name_parts).strip()

        item_num = regular_price = sale_price = ""
        for m in range(k, min(k + 12, len(lines))):
            if lines[m] == "Item number" and m + 1 < len(lines):
                item_num = lines[m + 1]
            elif lines[m].startswith("In-warehouse"):
                parts = lines[m].split()
                regular_price = parts[-1]
            elif lines[m].startswith("PRICE"):
                parts = lines[m].split()
                sale_price = parts[-1]
            elif lines[m] == "SAVE" or lines[m].startswith("Valid "):
                break

        coupons.append({
            "name": name,
            "item_number": item_num,
            "savings": savings_raw.replace("$", "").strip(),
            "savings_note": savings_note,
            "regular_price": regular_price,
            "sale_price": sale_price,
            "valid": valid_str,
        })
        i = k

    return coupons


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", action="store_true", help="Print raw page text only")
    args = parser.parse_args()

    # Connect to managed browser
    try:
        tabs = get_tabs()
    except Exception as e:
        print(json.dumps({"error": f"Cannot connect to browser at {DEVTOOLS_URL}: {e}"}))
        sys.exit(1)

    # Reuse existing Costco tab or open a new one
    target_id = ws_url = None
    opened = False
    for tab in tabs:
        if "costco.ca/coupons" in tab.get("url", ""):
            target_id = tab.get("id")
            ws_url = tab.get("webSocketDebuggerUrl")
            break

    if not target_id:
        tab = open_new_tab(COUPONS_URL)
        target_id = tab.get("id")
        ws_url = tab.get("webSocketDebuggerUrl")
        opened = True
        time.sleep(WAIT_SECONDS)

    js = "document.body.innerText.substring(0, 25000)"
    raw, err = cdp_eval(ws_url, js)

    if opened:
        close_tab(target_id)

    if err or not raw:
        print(json.dumps({"error": err or "No content extracted"}))
        sys.exit(1)

    if args.raw:
        print(raw)
        return

    coupons = parse_coupons(raw)
    print(json.dumps({
        "source": COUPONS_URL,
        "coupon_count": len(coupons),
        "coupons": coupons
    }, indent=2))


if __name__ == "__main__":
    main()
