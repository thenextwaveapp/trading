"""Candle sizes the engine and backtester can execute.

Every fixed-width Binance USD-M interval is listed. `1M` is visible in the
registry but disabled: calendar months are not fixed-width, so the gapless
bar checks and timestamp arithmetic cannot treat them as a constant step.
"""
DAY_MS = 86_400_000

# (value, label, milliseconds). Fixed-width intervals only.
TIMEFRAMES = (
    ("1m", "1 minute", 60_000),
    ("3m", "3 minutes", 180_000),
    ("5m", "5 minutes", 300_000),
    ("15m", "15 minutes", 900_000),
    ("30m", "30 minutes", 1_800_000),
    ("1h", "1 hour", 3_600_000),
    ("2h", "2 hours", 7_200_000),
    ("4h", "4 hours", 14_400_000),
    ("6h", "6 hours", 21_600_000),
    ("8h", "8 hours", 28_800_000),
    ("12h", "12 hours", 43_200_000),
    ("1d", "1 day", DAY_MS),
    ("3d", "3 days", 3 * DAY_MS),
    ("1w", "1 week", 7 * DAY_MS),
)

TIMEFRAME_MS = {value: ms for value, _label, ms in TIMEFRAMES}
TIMEFRAME_LABELS = {value: label for value, label, _ms in TIMEFRAMES}
TIMEFRAME_VALUES = tuple(TIMEFRAME_MS)
DEFAULT_TIMEFRAME = "15m"


def interval_ms(value):
    """Milliseconds per bar for a supported interval."""
    try:
        return TIMEFRAME_MS[value]
    except (KeyError, TypeError):
        raise ValueError(
            f"unsupported candle size: {value!r}; choose one of "
            f"{', '.join(TIMEFRAME_VALUES)}") from None


def interval_minutes(value):
    return interval_ms(value) // 60_000


def interval_label(value):
    return TIMEFRAME_LABELS.get(value, value)
