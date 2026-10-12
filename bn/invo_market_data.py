#!/usr/bin/env python3
"""Pull Hyperliquid market data around every Invo trade.
Usage: python3 invo_market_data.py invo_trades_XXXX.csv
Outputs (same folder): hl_candles_1h.csv.gz, hl_candles_15m.csv.gz, hl_funding.csv.gz, hl_coverage.csv
Standard library only. Uses Hyperliquid's public API (no login, no key)."""
import csv, gzip, json, random, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone
from collections import defaultdict

API = "https://api.hyperliquid.xyz/info"
H = 3600_000
TOP_N_FULL = 25          # tickers with the most trades: keep full 1h history and funding
DELAY = 0.25
LAST_ERROR = [""]

def post(body, tries=6):
    data = json.dumps(body).encode()
    for i in range(tries):
        try:
            req = urllib.request.Request(API, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                time.sleep(DELAY)
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            LAST_ERROR[0] = f"HTTP {e.code}: {e.read()[:300]!r}"
            if e.code == 429 or e.code >= 500:
                time.sleep(3 * (i + 1)); continue
            return None
        except Exception as e:
            LAST_ERROR[0] = f"{type(e).__name__}: {e}"
            if "CERTIFICATE_VERIFY_FAILED" in str(e):
                return None
            time.sleep(3 * (i + 1))
    return None

def ms(iso):
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)

def candles(coin, interval, step, start, end):
    out, s = {}, start
    while s < end:
        r = post({"type": "candleSnapshot", "req": {"coin": coin, "interval": interval, "startTime": s, "endTime": end}})
        if not r: break
        for c in r: out[c["t"]] = c
        last = max(c["t"] for c in r)
        if last + step <= s: break
        s = last + step
    return [out[k] for k in sorted(out)]

def funding(coin, start, end):
    out, s = {}, start
    while s < end:
        r = post({"type": "fundingHistory", "coin": coin, "startTime": s, "endTime": end})
        if not r: break
        for f in r: out[f["time"]] = f
        last = max(f["time"] for f in r)
        if last <= s: break
        s = last + 1
    return [out[k] for k in sorted(out)]

def main(path, sample=None):
    now = int(time.time() * 1000)
    trades = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("ticker") and r.get("opened_at")]
    if sample:
        random.seed(1)
        rows = random.sample(rows, min(sample, len(rows)))
        print(f"Test mode: {len(rows)} random trades")
    for row in rows:
        o = ms(row["opened_at"]); c = ms(row["closed_at"]) if row.get("closed_at") else now
        trades[row["ticker"]].append((o, c))
    order = sorted(trades, key=lambda k: -len(trades[k]))
    probe = post({"type": "candleSnapshot", "req": {"coin": "BTC", "interval": "1h", "startTime": now - 48 * H, "endTime": now}})
    if not probe:
        sys.exit("Test request to Hyperliquid failed, nothing pulled.\nError: " + LAST_ERROR[0] +
                 ("\nFix: open Finder > Applications > your Python folder and double-click 'Install Certificates.command', then rerun."
                  if "CERTIFICATE" in LAST_ERROR[0] else ""))
    print(f"Test request OK ({len(probe)} BTC candles).")
    top = set(order[:TOP_N_FULL])
    print(f"{len(order)} tickers, {sum(len(v) for v in trades.values())} trades")

    f1 = gzip.open("hl_candles_1h.csv.gz", "wt", newline=""); w1 = csv.writer(f1)
    f15 = gzip.open("hl_candles_15m.csv.gz", "wt", newline=""); w15 = csv.writer(f15)
    ff = gzip.open("hl_funding.csv.gz", "wt", newline=""); wf = csv.writer(ff)
    hdr = ["ticker", "coin", "t", "o", "h", "l", "c", "v", "n"]
    w1.writerow(hdr); w15.writerow(hdr); wf.writerow(["ticker", "coin", "time", "fundingRate", "premium"])
    cov = open("hl_coverage.csv", "w", newline=""); wc = csv.writer(cov)
    wc.writerow(["ticker", "coin", "trades", "first_entry", "c1h_kept", "c1h_earliest", "c15m_kept", "c15m_earliest", "funding_rows", "note"])

    for i, tk in enumerate(order, 1):
        ws = trades[tk]
        first = min(o for o, _ in ws); last = max(c for _, c in ws)
        coin, c1 = tk, None
        for cand in (tk, "k" + tk):
            c1 = candles(cand, "1h", H, first - 72 * H, min(last + 6 * H, now))
            if c1: coin = cand; break
        note = "" if c1 else ("no candles: " + LAST_ERROR[0])[:200]
        win1 = [(o - 72 * H, c + 6 * H) for o, c in ws]
        kept1 = [c for c in (c1 or []) if tk in top or any(a <= c["t"] <= b for a, b in win1)]
        for c in kept1: w1.writerow([tk, coin, c["t"], c["o"], c["h"], c["l"], c["c"], c["v"], c["n"]])
        kept15 = []
        if c1:
            c15 = candles(coin, "15m", H // 4, first - 24 * H, min(last + 2 * H, now))
            win15 = [(o - 24 * H, c + 2 * H) for o, c in ws]
            kept15 = [c for c in c15 if any(a <= c["t"] <= b for a, b in win15)]
            for c in kept15: w15.writerow([tk, coin, c["t"], c["o"], c["h"], c["l"], c["c"], c["v"], c["n"]])
        fr = []
        if c1 and tk in top:
            fr = funding(coin, first - 72 * H, min(last + 6 * H, now))
            for x in fr: wf.writerow([tk, coin, x["time"], x["fundingRate"], x.get("premium", "")])
        iso = lambda t: datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%Y-%m-%d") if t else ""
        wc.writerow([tk, coin, len(ws), iso(first), len(kept1), iso(c1[0]["t"]) if c1 else "",
                     len(kept15), iso(kept15[0]["t"]) if kept15 else "", len(fr), note])
        cov.flush()
        print(f"[{i}/{len(order)}] {tk}: {len(ws)} trades, 1h {len(kept1)}, 15m {len(kept15)}, funding {len(fr)} {note}")
    for f in (f1, f15, ff, cov): f.close()
    print("Done. Upload hl_candles_1h.csv.gz, hl_candles_15m.csv.gz, hl_funding.csv.gz and hl_coverage.csv.")

if __name__ == "__main__":
    if len(sys.argv) not in (2, 3): sys.exit("Usage: python3 invo_market_data.py invo_trades_XXXX.csv [number_of_trades]")
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) == 3 else None)
