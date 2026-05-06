"""Shared Bybit source configuration for local market-data fetch scripts."""

BYBIT_CATEGORY = "linear"
BYBIT_SYMBOLS = ("BTCUSDT", "ETHUSDT")
DEFAULT_BYBIT_SYMBOL = BYBIT_SYMBOLS[0]


def normalized_symbols(symbols: tuple[str, ...] = BYBIT_SYMBOLS) -> tuple[str, ...]:
    """Return uppercase symbols with stable order and duplicates removed."""
    seen = set()
    normalized = []
    for symbol in symbols:
        cleaned = symbol.strip().upper()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            normalized.append(cleaned)
    return tuple(normalized)


def symbol_slug(symbol: str) -> str:
    """Return the lower-case file-prefix form used by local parquet outputs."""
    return symbol.strip().lower()
