---
name: costco-coupons
description: Fetch, parse, and report current Costco Canada warehouse savings/coupons for Alberta. Use when Robison asks about current Costco deals, promotions, savings, or coupons — or when the weekly coupon check cron job runs. Also use to check for price adjustment opportunities against recent receipts.
---

# Costco Coupons

Fetch current Costco Canada savings offers for Alberta using the OpenClaw managed browser (CDP on port 18800), which has Costco cookies and bypasses bot detection.

## How it works

The `fetch-coupons.py` script:
1. Connects to the managed browser at `http://127.0.0.1:18800`
2. Reuses an existing `costco.ca/coupons` tab, or opens a new one and waits 6s for JS to render
3. Extracts `document.body.innerText` via CDP WebSocket (requires `websocket-client`)
4. Parses the text into structured coupon JSON
5. Closes any tab it opened (reuses existing tabs without closing them)

## Running the script

```bash
# Install dependency (one-time)
pip3 install websocket-client

# Fetch and parse coupons → JSON
python3 ~/.openclaw/skills/costco-coupons/scripts/fetch-coupons.py

# Dump raw page text (for debugging)
python3 ~/.openclaw/skills/costco-coupons/scripts/fetch-coupons.py --raw
```

## Output format

```json
{
  "source": "https://www.costco.ca/coupons.html",
  "coupon_count": 35,
  "coupons": [
    {
      "name": "Charmin Ultra Soft 2-ply bathroom tissue 30 × 200 sheets",
      "item_number": "2633624",
      "savings": "6.50",
      "savings_note": "",
      "regular_price": "$32.49",
      "sale_price": "$25.99",
      "valid": "Valid May 11 to 24, 2026 2 WEEKS"
    }
  ]
}
```

## Cron job (weekly Friday check)

The `costco-coupon-refund-check` cron job runs Fridays at 8am MT. Its job:
1. Run `fetch-coupons.py` to get current coupons
2. Run `coupon-check.py` (in `~/projects/grocery-receipt-parser/scripts/`) to match against recent receipts
3. Send Telegram message with refund opportunities (or a ✅ no-matches message)

**Important:** The cron job has a 5-minute timeout. The browser open + render step takes ~6-8s if a tab is already open. Keep the total script runtime under 4 minutes.

## Troubleshooting

- **"Cannot connect to browser"** — OpenClaw managed browser isn't running. Check `openclaw gateway status`.
- **"websocket-client not installed"** — Run `pip3 install websocket-client`.
- **Empty coupons list** — Page may not have rendered. Try `--raw` to inspect what was captured. Increase `WAIT_SECONDS` in the script if needed.
- **Bot detection / 403** — Don't use `curl` or `web_fetch` directly. Always use the managed browser (port 18800) which has real cookies.

## Fallback: AppleScript + screenshot

If CDP fails, use AppleScript to open the page in Chrome (requires "Allow JavaScript from Apple Events" enabled in Chrome > View > Developer) or take a screenshot with `screencapture` and parse via vision model.
