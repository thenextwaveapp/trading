#!/usr/bin/env python3
"""RANDOM DEGEN UNIVERSE — same strategy, same period, 60 RANDOM crypto
perps (TradFi perps excluded), three independent draws.

The placebo_universe_test picked the next-most-liquid tier, which pulled in
tokenized stocks/metals. This is the purer version of the question: does
the strategy work on any random pile of degen coins, or only on the coins
the Invo traders actually trade?

Usage: python3 research/random_degen_test.py
Writes: reports/random_degen_<stamp>.txt
"""
import random
from datetime import datetime, timezone

from rules_backtest import load
from degen_derby import precompute, START
from regime_switch_backtest import pump_events, make_dial
import super_larry as SL
from super_larry_wide import load_wide_era, LADDER

WDAYS, THR = 30, 0.0
N, SEEDS = 60, (1, 2, 3)

# tokenized stocks / ETFs / commodities / FX / pre-IPO perps seen in the
# wide cache — not degen coins, excluded from the random pool
TRADFI = set("""
AAOI AAPL ACN ADBE ALAB AMAT AMC AMD AMZN ANET ANTHROPIC APLD APP ARM ASML
ASTS AVGO AXTI BABA BE BILL BITO BMNR BRKB BX BYD BZ CIEN CL COHR COIN COPPER
COST CRCL CRDO CRM CRML CRWD CRWV CSCO CSOPSAMSUNG2L CSOPSKHYNIX2L CVNA CVX
CXMT DDOG DELL DIS DJT DKNG DRAM EBAY EWJ EWY EWZ F GDX GEV GLW GME GOOGL
GPRO GS GTLB HD HEI HIMS HK0625 HK0700 HK0992 HK1810 HOOD HPE HUT HYUNDAI
HANA HANMI IBM INTC IONQ IREN IWM JPM KLAC KO KODEX200 KORU KSTR KUAISHOU
LGELECTRONICS LLY LRCX MARA MDB MEITUAN META MINIMAX MP MRK MRNA MRVL MSFT
MSTR MU NAVER NATGAS NBIS NFLX NKE NOK NOW NVDA NVDL NVO OKLO ONDS OPENAI
ORCL OURA PANW PAYP PDD PLTR POPMART PYPL QCOM QQQ RDDT RIVN RKLB RUM
SAMSUNG SAMSUNGEM SECZ SHOP SKDD SKHY SKHYNIX SLX SMCI SMH SNDK SNOW SOFI
SONY SOXL SOXS SPCX SPY SQQQ TBT TENCENT TEM TER TMF TQQQ TSLA TSLL TSM
TTWO TWST TXN TZA UBER UNH UNITREE URNM USAR USDBRL UVXY V VRT VST WDC WMT
XAG XAU XAUT XBI XLE XOM XPD XPT ZHIPU ZHONGJI ZM ZS
""".split())

OUT = []
def p(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line, flush=True)


def run_ladder(tag, tickers, dial, regime_at):
    p(f"  [{tag}] {len(tickers)} tickers")
    p(f"  {'config':52s} {'$10k ->':>13s} {'maxdd':>7s} {'S':>5s} {'C':>5s} "
      f"{'skip':>6s} {'liq':>4s}")
    for name, cfg in LADDER:
        eq, maxdd, n_s, n_c, sk, lq = SL.run_book(tickers, dial, regime_at, cfg)
        p(f"  {name:52s} ${eq:>12,.0f} {maxdd*100:6.1f}% {n_s:5d} {n_c:5d} "
          f"{sk:6d} {lq:4d}")


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p(f"RANDOM DEGEN UNIVERSE TEST — {stamp}")
    p(f"2025-26 main window | {len(SEEDS)} draws of {N} random crypto perps "
      f"(TradFi excluded) vs the Invo 60")
    p("")

    curated, regime_at = load("backtest/r60_candles_15m.csv.gz",
                              "backtest/r60_candles_1h.csv.gz")
    t_lo = int(min(d["t"][0] for d in curated.values()))
    t_hi = int(max(d["t"][-1] for d in curated.values()))
    for d in curated.values():
        precompute(d)
    ev = pump_events(curated)
    run_ladder("INVO 60 (control)", curated, make_dial(*ev, WDAYS, THR),
               regime_at)
    p("")

    wide = load_wide_era(t_lo, t_hi, skip=set(curated))
    pool = sorted(tk for tk in wide if tk not in TRADFI)
    p(f"random pool: {len(pool)} crypto perps (of {len(wide)} wide, "
      f"{len(wide) - len(pool)} TradFi excluded)")
    p("")

    for seed in SEEDS:
        rng = random.Random(seed)
        draw = rng.sample(pool, N)
        uni = {tk: wide[tk] for tk in draw}
        for d in uni.values():
            precompute(d)
        p(f"  draw {seed}: " + " ".join(sorted(draw)))
        ev = pump_events(uni)
        p(f"  pump events: {len(ev[0]):,}")
        run_ladder(f"RANDOM DEGEN 60 — draw {seed}", uni,
                   make_dial(*ev, WDAYS, THR), regime_at)
        p("")

    fname = ("reports/random_degen_"
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.txt")
    with open(fname, "w") as fh:
        fh.write("\n".join(OUT) + "\n")
    print(f"\n[saved -> {fname}]")


if __name__ == "__main__":
    main()
