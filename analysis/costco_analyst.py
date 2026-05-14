#!/usr/bin/env python3
"""
Costco Savings Intelligence Analyst
=====================================
Modules:
  1. Purchase Cycle Predictor  — when will you need each item next?
  2. Price Tracker             — is today's price above/below historical avg?
  3. Coupon Collision Engine   — due soon + on coupon = buy now
  4. Spend Anomaly Detector    — flag outlier trips, track trends
  5. Savings Leakage Finder    — TPD capture rate, Executive ROI, price codes

Usage:
  python3 costco_analyst.py            # full report
  python3 costco_analyst.py --full     # verbose
  python3 costco_analyst.py --module 1 # single module
  python3 costco_analyst.py --json     # JSON output
"""

import sqlite3, statistics, json, sys, os, re, math
from datetime import datetime, date, timedelta
from pathlib import Path
from collections import defaultdict

DB_PATH   = Path.home() / ".grocery-receipts/db/groceries.db"
COUPONS_PATH = Path("/tmp/costco-coupons.json")
MIN_PURCHASES_FOR_CYCLE = 3
RESTOCK_ALERT_DAYS      = 7
OVERDUE_DAYS            = 5
PRICE_SPIKE_THRESHOLD   = 0.15
PRICE_DEAL_THRESHOLD    = 0.10
ANOMALY_ZSCORE          = 2.0
TODAY = date.today()

FULL_MODE = "--full" in sys.argv
JSON_MODE = "--json" in sys.argv
MODULE = None
if "--module" in sys.argv:
    idx = sys.argv.index("--module")
    MODULE = int(sys.argv[idx+1]) if idx+1 < len(sys.argv) else None

def conn():
    return sqlite3.connect(str(DB_PATH))

def fmt_date(d):
    if isinstance(d, str): d = datetime.strptime(d[:10], "%Y-%m-%d").date()
    delta = (TODAY - d).days
    if delta == 0:  return "today"
    if delta == 1:  return "yesterday"
    if delta < 0:   return f"in {-delta}d"
    if delta < 30:  return f"{delta}d ago"
    if delta < 365: return f"{delta//7}w ago"
    return d.strftime("%b %d %Y")

NORM_MAP = [
    (r"B/S THIGHS|B/S CHICKEN THIGHS|CHICKEN THIGHS|55501 THIGHS|55506.*", "CHICKEN THIGHS"),
    (r"B/S BREASTS|B/S CHICKEN BREASTS|CHICKEN BREASTS|55503.*", "CHICKEN BREASTS"),
    (r"KS SOUR CRM|KS SOUR CREAM", "KS SOUR CREAM"),
    (r"KS ORG BTR|KS ORGANIC BUTTER|KS ORG BUTTER", "KS ORGANIC BUTTER"),
    (r"BUTTER 454\s?G", "BUTTER 454G"),
    (r"COTTAGE CH?SE|COTTAGE CHEESE", "COTTAGE CHEESE"),
    (r"GRAPE TOMATO.*|GRAPE TOMATOES", "GRAPE TOMATO"),
    (r"MINI CUKE.*|MINI CUCUMBERS?", "MINI CUKES"),
    (r"GROUND BEEF|LEAN GR BEEF|LEAN GROUND BEEF|21928.*", "GROUND BEEF"),
    (r"KS BACON|104847.*", "KS BACON"),
    (r"TOP SIRLOIN|47325.*", "TOP SIRLOIN"),
    (r"KS PIZZA MOZ.*|KS PIZZA MOZZARELLA", "KS PIZZA MOZZARELLA"),
    (r"WHIP CREAM.*|WHIPPED CREAM.*", "WHIP CREAM 1L"),
    (r"KS APPLESAU.*|KS APPLESAUCE", "KS APPLESAUCE"),
    (r"KS PAPER TOWEL|KS TOWEL|580517.*", "KS PAPER TOWEL"),
    (r"KS BATH.*|KS BATH TISSUE|6262016.*", "KS BATH TISSUE"),
    (r"STRAWBERRIES?", "STRAWBERRIES"),
    (r"CLEMENTINES?|18600.*|21366.*", "CLEMENTINES"),
    (r"IL GREZZO.*|427141.*", "IL GREZZO OLIVE OIL"),
    (r"KS GREEK YOGURT|KS GRK YGRT|KS GRK YOGURT|434267.*", "KS GREEK YOGURT"),
    (r"ROTI CHICKEN|ROTCKNBYKG|ROTISSERIE CHICKEN.*", "ROTI CHICKEN"),
    (r"BRISKET|51337.*", "BRISKET"),
    (r"EYE OF ROUND", "EYE OF ROUND"),
    (r"BEAR PAWS|4428146.*", "BEAR PAWS"),
    (r"LAVAZZA.*|599010.*|493389.*", "LAVAZZA COFFEE"),
    (r"KS DIAPER.*|DIAPERS?.*|HUGGIES.*|1920493.*|955486.*", "DIAPERS"),
    (r"KS CAT ?FOOD|KS ND CAT|KS CATFOOD|261755.*|190379.*|KS CAT", "KS CAT FOOD"),
    (r"MANDARINS?|18600.*", "MANDARINS"),
    (r"CHOCOVIA|1906855.*", "CHOCOVIA"),
    (r"WHOLE CHICKEN|55505.*", "WHOLE CHICKEN"),
    (r"EYE OF ROUND|29339.*", "EYE OF ROUND"),
    (r"BOTTOM BLADE.*|21907.*", "BOTTOM BLADE ROAST"),
    (r"PORK BELLY|31483.*", "PORK BELLY"),
    (r"PORK LOIN|31097.*", "PORK LOIN"),
    (r"KS SOFTENER|1725830.*", "KS SOFTENER"),
    (r"KS BAGS.*|157089.*", "KS FREEZER BAGS"),
    (r"KS HOUSE.*|1726089.*", "KS HOUSE DRESSING"),
    (r"KS PURE SALT|384732.*", "KS PURE SALT"),
    (r"ORGANIC HONEY|ORGANIC HONY|130958.*", "ORGANIC HONEY"),
    (r"KS ORGANIC EGGS|313963.*", "KS ORGANIC EGGS"),
    (r"SWEET CHERRY|1859103.*", "SWEET CHERRY"),
    (r"ROMA TOMATO|171104.*", "ROMA TOMATO"),
]

def normalize_name(name):
    n = name.upper().strip()
    for pattern, replacement in NORM_MAP:
        if re.fullmatch(pattern, n):
            return replacement
    return n

def load_purchases():
    c = conn()
    rows = c.execute("""
        SELECT i.name, i.total_price, r.receipt_date, r.id, r.store_name
        FROM items i JOIN receipts r ON i.receipt_id = r.id
        WHERE i.total_price > 0 AND r.total_amount > 0
        ORDER BY r.receipt_date
    """).fetchall()
    c.close()
    purchases = defaultdict(list)
    for name, price, dt, rid, store in rows:
        norm = normalize_name(name)
        purchases[norm].append({
            "date":  datetime.strptime(dt[:10], "%Y-%m-%d").date(),
            "price": price, "receipt_id": rid, "store": store, "raw_name": name,
        })
    return purchases

def load_receipts():
    c = conn()
    rows = c.execute("""
        SELECT id, store_name, store_location, receipt_date, total_amount
        FROM receipts WHERE total_amount > 0 ORDER BY receipt_date
    """).fetchall()
    c.close()
    return [{"id":r[0],"store":r[1],"location":r[2],
             "date":datetime.strptime(r[3][:10],"%Y-%m-%d").date(),"total":r[4]} for r in rows]

def load_coupons():
    if COUPONS_PATH.exists():
        with open(COUPONS_PATH) as f:
            data = json.load(f)
        if isinstance(data, list): return data
        return data.get("coupons", data.get("items", []))
    return []

# ── MODULE 1: Purchase Cycle Predictor ────────────────────────────────────────
def module_purchase_cycles(purchases):
    results = []
    for name, buys in purchases.items():
        if len(buys) < MIN_PURCHASES_FOR_CYCLE: continue
        dates = sorted(b["date"] for b in buys)
        gaps  = [(dates[i+1]-dates[i]).days for i in range(len(dates)-1) if 0 < (dates[i+1]-dates[i]).days < 365]
        if not gaps: continue
        avg_cycle = statistics.mean(gaps)
        std_cycle = statistics.stdev(gaps) if len(gaps) > 1 else 0
        last_buy  = dates[-1]
        predicted = last_buy + timedelta(days=round(avg_cycle))
        days_until = (predicted - TODAY).days
        cv = std_cycle / avg_cycle if avg_cycle > 0 else 1
        confidence = max(0, min(100, round((1 - cv) * 100)))
        if days_until < -OVERDUE_DAYS:   status, emoji = "OVERDUE",   "🚨"
        elif days_until <= RESTOCK_ALERT_DAYS: status, emoji = "DUE_SOON", "⏰"
        elif days_until <= 14:            status, emoji = "UPCOMING",  "📅"
        else:                             status, emoji = "OK",        "✅"
        prices = [b["price"] for b in buys]
        results.append({
            "name": name, "buy_count": len(buys),
            "avg_cycle_days": round(avg_cycle,1), "std_cycle_days": round(std_cycle,1),
            "confidence_pct": confidence,
            "last_buy_date": last_buy, "days_since": (TODAY-last_buy).days,
            "predicted_next": predicted, "days_until": days_until,
            "status": status, "emoji": emoji,
            "avg_price": round(statistics.mean(prices),2),
            "last_price": round(prices[-1],2), "all_prices": prices,
        })
    results.sort(key=lambda x: x["days_until"])
    return results

# ── MODULE 2: Price Tracker ───────────────────────────────────────────────────
def module_price_tracker(purchases):
    results = []
    for name, buys in purchases.items():
        if len(buys) < 2: continue
        prices = [b["price"] for b in buys]
        avg_price  = statistics.mean(prices)
        last_price = prices[-1]
        n = len(prices)
        if n >= 3:
            x  = list(range(n)); xm = statistics.mean(x); ym = avg_price
            num = sum((x[i]-xm)*(prices[i]-ym) for i in range(n))
            den = sum((x[i]-xm)**2 for i in range(n))
            slope = num/den if den else 0
        else: slope = 0
        pct_vs_avg = (last_price - avg_price) / avg_price if avg_price else 0
        if   pct_vs_avg >=  PRICE_SPIKE_THRESHOLD: sig, em = "HIGH",   "📈"
        elif pct_vs_avg <= -PRICE_DEAL_THRESHOLD:  sig, em = "DEAL",   "💰"
        else:                                       sig, em = "NORMAL", "➡️"
        trend = "↑ rising" if slope > 0.3 else "↓ falling" if slope < -0.3 else "→ stable"
        results.append({
            "name": name, "buy_count": len(buys),
            "avg_price": round(avg_price,2), "min_price": round(min(prices),2),
            "max_price": round(max(prices),2), "last_price": round(last_price,2),
            "last_date": buys[-1]["date"],
            "pct_vs_avg": round(pct_vs_avg*100,1), "trend": trend,
            "slope": round(slope,3), "price_signal": sig, "price_emoji": em,
        })
    results.sort(key=lambda x: abs(x["pct_vs_avg"]), reverse=True)
    return results

# ── MODULE 3: Coupon Collision Engine ─────────────────────────────────────────
def module_coupon_collision(cycles, prices, coupons):
    if not coupons: return [], "No coupon data. Run: openclaw fetch coupons"
    cycle_map = {r["name"].upper(): r for r in cycles}
    price_map  = {r["name"].upper(): r for r in prices}
    alerts = []
    for coupon in coupons:
        raw      = coupon.get("item", coupon.get("name", coupon.get("product", "")))
        discount = coupon.get("savings", coupon.get("discount", coupon.get("amount", 0)))
        expiry   = coupon.get("expiry", coupon.get("end_date", coupon.get("valid_until", "")))
        if not raw: continue
        coupon_words = set(raw.upper().split())
        best_match, best_score = None, 0
        for known in list(cycle_map.keys()) + list(price_map.keys()):
            overlap = len(coupon_words & set(known.split()))
            score   = overlap + (0.5 if overlap >= 2 else 0)
            if score > best_score:
                best_score, best_match = score, known
        if not best_match or best_score < 1: continue
        score, reasons = 0, []
        ci = cycle_map.get(best_match)
        pi = price_map.get(best_match)
        if ci:
            if   ci["status"] == "OVERDUE":  score += 40; reasons.append("overdue — buy now")
            elif ci["status"] == "DUE_SOON": score += 30; reasons.append(f"due in {ci['days_until']}d")
            elif ci["status"] == "UPCOMING": score += 15; reasons.append(f"due in {ci['days_until']}d — stock up")
            else:                             score +=  5; reasons.append("save for next cycle")
        if pi and pi["avg_price"] > 20: score += 10; reasons.append(f"avg ${pi['avg_price']:.2f}")
        if isinstance(discount,(int,float)) and discount > 0: score += min(20, int(discount*3))
        tier = "🔥 BUY NOW" if score>=50 else "⚡ STOCK UP" if score>=25 else "👀 CONSIDER" if score>=10 else "ℹ️ FYI"
        alerts.append({"tier":tier,"score":score,"coupon_raw":raw,"matched_to":best_match.title(),
                        "discount":discount,"expiry":expiry,"reasons":reasons,"cycle":ci,"price":pi})
    alerts.sort(key=lambda x: x["score"], reverse=True)
    return alerts, None

# ── MODULE 4: Spend Analysis ──────────────────────────────────────────────────
def module_spend_analysis(receipts):
    if not receipts: return {}
    totals  = [r["total"] for r in receipts]
    avg_t   = statistics.mean(totals)
    std_t   = statistics.stdev(totals) if len(totals)>1 else 0
    anomalies = [{**r,"z_score":round((r["total"]-avg_t)/std_t,2)} for r in receipts if std_t and abs((r["total"]-avg_t)/std_t)>=ANOMALY_ZSCORE]
    monthly = defaultdict(lambda:{"total":0,"trips":0})
    for r in receipts:
        m = r["date"].strftime("%Y-%m")
        monthly[m]["total"] += r["total"]; monthly[m]["trips"] += 1
    dow_map  = {0:"Sun",1:"Mon",2:"Tue",3:"Wed",4:"Thu",5:"Fri",6:"Sat"}
    dow_counts = defaultdict(int)
    for r in receipts: dow_counts[dow_map[r["date"].weekday()]] += 1
    date_range  = (receipts[-1]["date"]-receipts[0]["date"]).days
    months_span = max(1, date_range/30.44)
    total_spent = sum(totals)
    trend_months = sorted(monthly.keys())[-3:]
    return {
        "total_spent": round(total_spent,2), "total_trips": len(receipts),
        "avg_trip": round(avg_t,2), "max_trip": round(max(totals),2),
        "min_trip": round(min(totals),2), "std_trip": round(std_t,2),
        "monthly_avg": round(total_spent/months_span,2), "months_span": round(months_span,1),
        "anomalies": sorted(anomalies,key=lambda x:x["z_score"],reverse=True),
        "monthly": {k:{"total":round(v["total"],2),"trips":v["trips"]} for k,v in monthly.items()},
        "dow_counts": dict(dow_counts),
        "trend_3mo": [(m, round(monthly[m]["total"],2)) for m in trend_months],
        "date_start": receipts[0]["date"].isoformat(), "date_end": receipts[-1]["date"].isoformat(),
    }

# ── MODULE 5: Savings Leakage Finder ─────────────────────────────────────────
def module_savings_leakage(purchases, receipts):
    insights = []

    # 5a: TPD Capture Rate
    c = conn()
    tpd_rows = c.execute("""
        SELECT ABS(i.total_price) FROM items i JOIN receipts r ON i.receipt_id=r.id
        WHERE i.total_price < 0 AND UPPER(i.name) LIKE 'TPD/%'
    """).fetchall()
    c.close()
    total_tpd = sum(r[0] for r in tpd_rows)
    insights.append({
        "category": "TPD Instant Savings",
        "finding": f"You captured ${total_tpd:.2f} in instant savings across {len(tpd_rows)} TPD discounts.",
        "grade": "A" if len(tpd_rows)>30 else "B",
        "tip": "TPDs reset monthly. Check the coupon book before each trip — load your shopping list accordingly."
    })

    # 5b: Executive Membership ROI
    spend = module_spend_analysis(receipts)
    annual = spend["monthly_avg"] * 12
    reward = annual * 0.02
    upgrade_roi = reward - 65
    insights.append({
        "category": "Executive Membership ROI",
        "finding": f"At ${spend['monthly_avg']:.0f}/mo avg (${annual:.0f}/yr), 2% Executive cashback = ${reward:.0f}/yr.",
        "grade": "A" if upgrade_roi > 0 else "C",
        "tip": f"Net benefit after $65 upgrade cost: ${upgrade_roi:.0f}/yr. "
               + ("Worth it." if upgrade_roi > 0 else "Not worth it at current spend.")
    })

    # 5c: Price adjustment candidates (bought above avg in last 30 days)
    cutoff = TODAY - timedelta(days=30)
    adj_candidates = []
    for name, buys in purchases.items():
        recent = [b for b in buys if b["date"] >= cutoff]
        if not recent: continue
        all_p = [b["price"] for b in buys]
        if len(all_p) < 3: continue
        hist_avg = statistics.mean(all_p[:-len(recent)])
        paid     = recent[-1]["price"]
        if paid > hist_avg * 1.05:
            adj_candidates.append({"name":name,"paid":paid,"avg":round(hist_avg,2),
                                   "overpaid":round(paid-hist_avg,2),"bought":recent[-1]["date"].isoformat()})
    insights.append({
        "category": "30-Day Price Adjustment Candidates",
        "finding": f"{len(adj_candidates)} item(s) bought recently above your historical avg.",
        "grade": "info",
        "tip": "Costco adjusts prices within 30 days — bring your receipt to the membership desk.",
        "detail": adj_candidates[:5],
    })

    # 5d: Meat price intelligence (your biggest category)
    meat_items = ["TOP SIRLOIN","GROUND BEEF","BRISKET","KS BACON","CHICKEN BREASTS","CHICKEN THIGHS"]
    meat_findings = []
    for item in meat_items:
        if item in purchases:
            prices = [b["price"] for b in purchases[item]]
            if len(prices) >= 3:
                cv = statistics.stdev(prices)/statistics.mean(prices)
                meat_findings.append(f"{item.title()}: ${statistics.mean(prices):.2f} avg "
                                      f"(${min(prices):.2f}–${max(prices):.2f}, CV={cv:.0%})")
    insights.append({
        "category": "Meat Price Intelligence",
        "finding": "\n  ".join(meat_findings) if meat_findings else "Not enough data",
        "grade": "B",
        "tip": "Meat = 31% of your spend ($7,783). When Top Sirloin < $60 or Ground Beef < $35, buy 2 packs and freeze."
    })

    # 5e: Shopping day efficiency
    c = conn()
    dow_rows = c.execute("""
        SELECT strftime('%w',receipt_date), COUNT(*), AVG(total_amount)
        FROM receipts WHERE total_amount > 0 GROUP BY strftime('%w',receipt_date)
    """).fetchall()
    c.close()
    dow_names = {"0":"Sun","1":"Mon","2":"Tue","3":"Wed","4":"Thu","5":"Fri","6":"Sat"}
    dow_avgs  = {dow_names[r[0]]: round(r[2],2) for r in dow_rows}
    best_day  = min(dow_avgs, key=dow_avgs.get)
    worst_day = max(dow_avgs, key=dow_avgs.get)
    insights.append({
        "category": "Shopping Day Efficiency",
        "finding": " | ".join(f"{d}=${v:.0f}" for d,v in sorted(dow_avgs.items())),
        "grade": "info",
        "tip": f"You spend least on {best_day}s (avg ${dow_avgs[best_day]:.0f}) and most on {worst_day}s "
               f"(avg ${dow_avgs[worst_day]:.0f}). Saturday = freshest stock. Weekday = shorter lines."
    })

    # 5f: Costco price code cheatsheet
    insights.append({
        "category": "Costco Price Code Guide",
        "finding": "Price codes to watch in-store:",
        "grade": "info",
        "tip": (
            ".97 = manager's clearance (deepest discount, limited stock)\n"
            "  .88 / .00 = needs to move fast (buy if you use it)\n"
            "  .49/.79/.89 = manufacturer special\n"
            "  ✱ asterisk on tag = NOT being restocked — last chance\n"
            "  No asterisk = regular item, safe to pass if not on sale"
        )
    })

    return insights

# ── Report Formatter ──────────────────────────────────────────────────────────
def format_report(cycles, prices, coupon_alerts, coupon_error, spend, leakage):
    L = []
    L.append(f"🛒 COSTCO SAVINGS INTELLIGENCE")
    L.append(f"📅 {TODAY.strftime('%B %d, %Y')}\n")

    # Restock Radar
    L.append("━━━━ 📦 RESTOCK RADAR ━━━━")
    urgent   = [c for c in cycles if c["status"] in ("OVERDUE","DUE_SOON")]
    upcoming = [c for c in cycles if c["status"] == "UPCOMING"]
    if urgent:
        for item in urgent[:10]:
            d = item["days_until"]
            lbl = f"OVERDUE {-d}d" if d < 0 else f"in {d}d"
            L.append(f"  {item['emoji']} {item['name'].title():<28} {lbl:<13} (every ~{item['avg_cycle_days']:.0f}d)")
    else:
        L.append("  ✅ No urgent restocks right now")
    if upcoming:
        L.append("  📅 Coming up (7–14 days):")
        for item in upcoming[:5]:
            L.append(f"     {item['name'].title():<28} in {item['days_until']}d")

    # Coupon Alerts
    L.append("\n━━━━ 🎟️  COUPON ALERTS ━━━━")
    if coupon_error:
        L.append(f"  ⚠️  {coupon_error}")
    elif not coupon_alerts:
        L.append("  No matches for your buying patterns this week.")
    else:
        for a in coupon_alerts[:8]:
            disc = f"${a['discount']:.2f} off" if isinstance(a["discount"],(int,float)) and a["discount"]>0 else ""
            exp  = f" · exp {a['expiry']}" if a["expiry"] else ""
            rsn  = " · ".join(a["reasons"]) if a["reasons"] else ""
            L.append(f"  {a['tier']}  {a['coupon_raw']}")
            L.append(f"    {disc}{exp} — {rsn}")

    # Price Signals
    L.append("\n━━━━ 💰 PRICE SIGNALS ━━━━")
    deals = [p for p in prices if p["price_signal"]=="DEAL"]
    highs = [p for p in prices if p["price_signal"]=="HIGH"]
    if deals:
        L.append("  🟢 Below your avg (consider buying extra):")
        for p in deals[:5]:
            L.append(f"     {p['name'].title():<28} ${p['last_price']:.2f} vs avg ${p['avg_price']:.2f} ({p['pct_vs_avg']:+.0f}%)")
    if highs:
        L.append("  🔴 Above your avg (buy minimum):")
        for p in highs[:5]:
            L.append(f"     {p['name'].title():<28} ${p['last_price']:.2f} vs avg ${p['avg_price']:.2f} ({p['pct_vs_avg']:+.0f}%)")
    if not deals and not highs:
        L.append("  ➡️  All tracked items near normal price range")

    # Spend Summary
    L.append("\n━━━━ 📊 SPEND SUMMARY ━━━━")
    L.append(f"  Receipts:     {spend['total_trips']}  |  Total: ${spend['total_spent']:,.2f}")
    L.append(f"  Monthly avg:  ${spend['monthly_avg']:,.2f}  |  Avg trip: ${spend['avg_trip']:.2f}")
    if spend["trend_3mo"]:
        L.append("  Last 3 months: " + "  →  ".join(f"{m[5:]}: ${v:,.0f}" for m,v in spend["trend_3mo"]))
    if spend["anomalies"]:
        L.append(f"  ⚠️  Big trips: " + ", ".join(f"${a['total']:.0f} ({a['date']})" for a in spend["anomalies"][:3]))

    # Savings Insights
    L.append("\n━━━━ 🔍 SAVINGS INSIGHTS ━━━━")
    for ins in leakage:
        grade = f"[{ins['grade']}] " if ins["grade"] != "info" else ""
        L.append(f"  • {grade}{ins['category']}: {ins['finding'].splitlines()[0]}")
        if FULL_MODE:
            L.append(f"    💡 {ins['tip']}")
            if "detail" in ins:
                for d in ins["detail"]:
                    L.append(f"       - {d['name'].title()}: paid ${d['paid']:.2f} vs avg ${d['avg']:.2f} (+${d['overpaid']:.2f}) on {d['bought']}")

    L.append(f"\n{'─'*50}")
    L.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(L)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not DB_PATH.exists():
        print(f"❌ DB not found: {DB_PATH}"); sys.exit(1)

    purchases = load_purchases()
    receipts  = load_receipts()
    coupons   = load_coupons()

    cycles   = module_purchase_cycles(purchases)  if MODULE in (None,1) else []
    prices   = module_price_tracker(purchases)    if MODULE in (None,2) else []
    c_alerts, c_err = module_coupon_collision(cycles,prices,coupons) if MODULE in (None,3) else ([],None)
    spend    = module_spend_analysis(receipts)    if MODULE in (None,4) else {}
    leakage  = module_savings_leakage(purchases,receipts) if MODULE in (None,5) else []

    if JSON_MODE:
        def default(o):
            if isinstance(o, (date,datetime)): return o.isoformat()
            raise TypeError
        print(json.dumps({"generated":datetime.now().isoformat(),"cycles":cycles[:50],
                          "prices":prices[:50],"coupon_alerts":c_alerts,"spend":spend,
                          "leakage":leakage},default=default,indent=2))
        return

    if MODULE == 1:
        print(f"{'Item':<32} {'Buys':>4}  {'Cycle':>6}  {'Last Buy':<12} {'Next Due':<12} Status")
        print("-"*85)
        for r in cycles:
            print(f"{r['name'].title():<32} {r['buy_count']:>4}  {r['avg_cycle_days']:>5.0f}d  "
                  f"{fmt_date(r['last_buy_date']):<12} {fmt_date(r['predicted_next']):<12} "
                  f"{r['emoji']} {r['status']}")
        return

    if MODULE == 2:
        print(f"{'Item':<32} {'Buys':>4}  {'Avg':>7}  {'Last':>7}  {'vs Avg':>7}  {'Trend':<10}  Signal")
        print("-"*85)
        for r in prices:
            print(f"{r['name'].title():<32} {r['buy_count']:>4}  {r['avg_price']:>7.2f}  "
                  f"{r['last_price']:>7.2f}  {r['pct_vs_avg']:>+6.1f}%  {r['trend']:<10}  "
                  f"{r['price_emoji']} {r['price_signal']}")
        return

    if MODULE == 4:
        print(f"Total: {spend['total_trips']} trips  ${spend['total_spent']:,.2f}  Avg/mo: ${spend['monthly_avg']:.2f}\n")
        for month, data in sorted(spend["monthly"].items()):
            bar = "█" * int(data["total"]/100)
            print(f"  {month}  ${data['total']:>8,.2f}  {data['trips']:>2} trips  {bar}")
        if spend["anomalies"]:
            print(f"\n⚠️  Anomaly trips:")
            for a in spend["anomalies"][:5]:
                print(f"  {a['date']}  ${a['total']:.2f}  (z={a['z_score']:+.1f})")
        return

    if MODULE == 5:
        for ins in leakage:
            print(f"\n📌 {ins['category']} [{ins['grade']}]\n   {ins['finding']}\n   💡 {ins['tip']}")
            if "detail" in ins:
                for d in ins["detail"]:
                    print(f"      - {d['name'].title()}: paid ${d['paid']:.2f} vs avg ${d['avg']:.2f} on {d['bought']}")
        return

    print(format_report(cycles, prices, c_alerts, c_err, spend, leakage))

if __name__ == "__main__":
    main()
