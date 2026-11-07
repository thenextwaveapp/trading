"""Entity resolution: event text -> the instrument(s) it concerns.

Returns [(instrument, confidence)] pairs; zero pairs means the event is dropped
(no instrument, no signal). Two signal sources:

  - explicit cashtags / tickers in the text ($BTC, $TSLA) — high confidence;
  - implicit mentions via an alias table (company/project name, or an exchange
    whose native token is implied, e.g. "Binance" -> BNB) — lower confidence,
    because the mapping is inferred rather than stated.

The alias table is the one piece that must be maintained as coverage grows. It
is intentionally small and explicit here, not a model — resolution confidence is
then a real, legible number the downstream confidence score consumes.
"""
import re

# base symbol -> alias phrases (lowercased, word-boundary matched). An exchange
# maps to its native token because that is what a hack/incident headline moves.
ALIASES = {
    "BTC": ("bitcoin",),
    "ETH": ("ethereum", "ether"),
    "SOL": ("solana",),
    "BNB": ("binance", "bnb chain"),
    "XRP": ("ripple",),
    "DOGE": ("dogecoin",),
    "TSLA": ("tesla",),
    "AAPL": ("apple",),
}

_CASHTAG = re.compile(r"\$([A-Za-z]{2,10})\b")


def resolve(text: str, known_symbols=None):
    """Resolve `text` to [(instrument, confidence)].

    `known_symbols`: optional set/dict of tradeable base symbols (from
    pf_instruments) used to confirm a cashtag is real and to disambiguate.
    """
    text = text or ""
    low = text.lower()
    found = {}

    for m in _CASHTAG.finditer(text):
        sym = m.group(1).upper()
        if known_symbols is None or sym in known_symbols:
            # a stated cashtag is a strong, explicit signal
            found[sym] = max(found.get(sym, 0.0), 0.95)

    for sym, phrases in ALIASES.items():
        if known_symbols is not None and sym not in known_symbols:
            continue
        for p in phrases:
            if re.search(r"\b" + re.escape(p) + r"\b", low):
                # inferred mapping: confident but not stated-ticker confident
                found[sym] = max(found.get(sym, 0.0), 0.8)
                break

    # ambiguity penalty: if the text resolved to several instruments, each is a
    # bit less certain to be the one that matters.
    n = len(found)
    if n > 1:
        found = {s: c * (1.0 - 0.1 * (n - 1)) for s, c in found.items()}
    return sorted(found.items(), key=lambda kv: -kv[1])
