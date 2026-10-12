#!/usr/bin/env python3
"""Pull Binance futures market data (Binance Vision archive) around every Invo trade.
Usage: python3 invo_binance_data.py invo_trades_XXXX.csv [number_of_trades]
Outputs: bn_candles_1h.csv.gz, bn_candles_15m.csv.gz, bn_funding.csv.gz, bn_coverage.csv
Standard library only. Free public archive, no login or key."""
import csv, gzip, io, random, re, sys, time, urllib.request, urllib.error, zipfile
from datetime import datetime, timezone, timedelta
from collections import defaultdict

LIST = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
FILES = "https://data.binance.vision/"
H = 3600_000
TOP_N_FULL = 25
LAST_ERROR = [""]

def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            LAST_ERROR[0] = f"HTTP {e.code} {url}"
            if e.code == 404: return None
            if e.code < 500: return None
        except Exception as e:
            LAST_ERROR[0] = f"{type(e).__name__}: {e}"
            if "CERTIFICATE_VERIFY_FAILED" in str(e): return None
        time.sleep(2 * (i + 1))
    return None

def list_keys(prefix):
    keys, marker = [], ""
    while True:
        url = f"{LIST}?prefix={prefix}&delimiter=/" + (f"&marker={marker}" if marker else "")
        body = get(url)
        if body is None: return None
        txt = body.decode()
        page = re.findall(r"<Key>(.*?)</Key>", txt)
        keys += page
        if "<IsTruncated>true</IsTruncated>" not in txt or not page: return keys
        marker = page[-1]

def ms(iso):
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)

def months_between(a, b):
    d = datetime.fromtimestamp(a / 1000, timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = datetime.fromtimestamp(b / 1000, timezone.utc)
    while d <= end:
        yield d.strftime("%Y-%m")
        d = (d + timedelta(days=32)).replace(day=1)

def days_between(a, b):
    d = datetime.fromtimestamp(a / 1000, timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    end = datetime.fromtimestamp(b / 1000, timezone.utc)
    while d <= end:
        yield d.strftime("%Y-%m-%d")
        d += timedelta(days=1)

def read_zip(blob):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        with z.open(z.namelist()[0]) as f:
            return list(csv.reader(io.TextIOWrapper(f, encoding="utf-8")))

def norm_ts(x):
    t = int(float(x))
    return t // 1000 if t > 10**14 else t

def klines(symbol, interval, ranges):
    """Fetch klines covering ranges [(start_ms, end_ms)], monthly files first, daily files for months not yet published."""
    base_m = f"data/futures/um/monthly/klines/{symbol}/{interval}/"
    base_d = f"data/futures/um/daily/klines/{symbol}/{interval}/"
    have_m = list_keys(base_m)
    if not have_m: return None
    have_m = {k for k in have_m if k.endswith(".zip")}
    lo, hi = min(a for a, _ in ranges), max(b for _, b in ranges)
    rows = {}
    missing_months = []
    for m in months_between(lo, hi):
        key = f"{base_m}{symbol}-{interval}-{m}.zip"
        if key not in have_m:
            missing_months.append(m); continue
        blob = get(FILES + key)
        if blob:
            for r in read_zip(blob):
                if r and r[0].strip().lstrip("-").isdigit(): rows[norm_ts(r[0])] = r
    if missing_months:
        have_d = {k for k in (list_keys(base_d) or []) if k.endswith(".zip")}
        for day in days_between(lo, hi):
            if day[:7] not in missing_months: continue
            key = f"{base_d}{symbol}-{interval}-{day}.zip"
            if key not in have_d: continue
            blob = get(FILES + key)
            if blob:
                for r in read_zip(blob):
                    if r and r[0].strip().lstrip("-").isdigit(): rows[norm_ts(r[0])] = r
    return [rows[t] for t in sorted(rows)]

def funding(symbol, lo, hi):
    base = f"data/futures/um/monthly/fundingRate/{symbol}/"
    have = {k for k in (list_keys(base) or []) if k.endswith(".zip")}
    out = []
    for m in months_between(lo, hi):
        key = f"{base}{symbol}-fundingRate-{m}.zip"
        if key not in have: continue
        blob = get(FILES + key)
        if not blob: continue
        for r in read_zip(blob):
            if r and r[0].strip().isdigit(): out.append((norm_ts(r[0]), r[-1]))
    return out

def candidates(tk):
    base = tk[1:] if tk.startswith("k") and tk[1:].isupper() else tk
    c = [f"{tk}USDT", f"1000{base}USDT", f"{base}USDT", f"1000000{base}USDT"]
    return list(dict.fromkeys(c))

def main(path, sample=None):
    now = int(time.time() * 1000)
    probe = list_keys("data/futures/um/monthly/klines/BTCUSDT/1h/")
    if not probe:
        sys.exit("Test request to Binance Vision failed, nothing pulled.\nError: " + LAST_ERROR[0])
    print(f"Test request OK ({len(probe)} BTC files listed).")

    with open(path, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("ticker") and r.get("opened_at")]
    if sample:
        random.seed(1)
        rows = random.sample(rows, min(sample, len(rows)))
        print(f"Test mode: {len(rows)} random trades")
    trades = defaultdict(list)
    for r in rows:
        o = ms(r["opened_at"]); c = ms(r["closed_at"]) if r.get("closed_at") else now
        trades[r["ticker"]].append((o, c))
    order = sorted(trades, key=lambda k: -len(trades[k]))
    top = set(order[:TOP_N_FULL])
    print(f"{len(order)} tickers, {len(rows)} trades")

    hdr = ["ticker", "symbol", "t", "o", "h", "l", "c", "v", "n", "taker_buy_v"]
    f1 = gzip.open("bn_candles_1h.csv.gz", "wt", newline=""); w1 = csv.writer(f1); w1.writerow(hdr)
    f15 = gzip.open("bn_candles_15m.csv.gz", "wt", newline=""); w15 = csv.writer(f15); w15.writerow(hdr)
    ff = gzip.open("bn_funding.csv.gz", "wt", newline=""); wf = csv.writer(ff); wf.writerow(["ticker", "symbol", "time", "fundingRate"])
    cov = open("bn_coverage.csv", "w", newline=""); wc = csv.writer(cov)
    wc.writerow(["ticker", "symbol", "trades", "first_entry", "c1h_kept", "c1h_earliest", "c15m_kept", "c15m_earliest", "funding_rows", "note"])
    iso = lambda t: datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%Y-%m-%d")

    for i, tk in enumerate(order, 1):
        ws = trades[tk]
        first = min(o for o, _ in ws); last = max(c for _, c in ws)
        win1 = [(o - 72 * H, c + 6 * H) for o, c in ws]
        win15 = [(o - 24 * H, c + 2 * H) for o, c in ws]
        rng1 = [(first - 72 * H, last + 6 * H)] if tk in top else win1
        sym, c1 = None, None
        for cand in candidates(tk):
            c1 = klines(cand, "1h", rng1)
            if c1 is not None: sym = cand; break
        kept1, kept15, fr, note = [], [], [], ""
        if sym is None:
            note = "not on Binance futures"
        else:
            for r in c1:
                t = norm_ts(r[0])
                if tk in top and rng1[0][0] <= t <= rng1[0][1] or any(a <= t <= b for a, b in win1):
                    kept1.append(r); w1.writerow([tk, sym, t, r[1], r[2], r[3], r[4], r[5], r[8], r[9]])
            c15 = klines(sym, "15m", win15) or []
            for r in c15:
                t = norm_ts(r[0])
                if any(a <= t <= b for a, b in win15):
                    kept15.append(r); w15.writerow([tk, sym, t, r[1], r[2], r[3], r[4], r[5], r[8], r[9]])
            if tk in top:
                fr = [x for x in funding(sym, first - 72 * H, last + 6 * H) if first - 72 * H <= x[0] <= last + 6 * H]
                for t, rate in fr: wf.writerow([tk, sym, t, rate])
            if not kept1: note = "listed, but no data in trade windows (likely listed after the trades)"
        wc.writerow([tk, sym or "", len(ws), iso(first), len(kept1), iso(norm_ts(kept1[0][0])) if kept1 else "",
                     len(kept15), iso(norm_ts(kept15[0][0])) if kept15 else "", len(fr), note])
        cov.flush()
        print(f"[{i}/{len(order)}] {tk} -> {sym or '-'}: {len(ws)} trades, 1h {len(kept1)}, 15m {len(kept15)}, funding {len(fr)} {note}")
    for f in (f1, f15, ff, cov): f.close()
    print("Done. Upload bn_candles_1h.csv.gz, bn_candles_15m.csv.gz, bn_funding.csv.gz and bn_coverage.csv.")

if __name__ == "__main__":
    if len(sys.argv) not in (2, 3): sys.exit("Usage: python3 invo_binance_data.py invo_trades_XXXX.csv [number_of_trades]")
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) == 3 else None)
