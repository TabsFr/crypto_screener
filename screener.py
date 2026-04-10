import os
import requests
import pandas as pd


# =========================
# Config
# =========================
TOP_N = 50
LOOKBACKS = [3, 7, 30]
OUTPUT_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "crypto_relative_strength.csv",
)
BYBIT_URL = "https://api.bybit.com/v5/market/kline"
BYBIT_INSTRUMENTS_URL = "https://api.bybit.com/v5/market/instruments-info"
COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets"
STABLECOINS = {
    "USDT",
    "USDC",
    "USDE",
    "USDS",
    "USDD",
    "DAI",
    "FDUSD",
    "TUSD",
    "PYUSD",
    "USDP",
    "USD1",
    "USDG",
    "USDF",
    "GUSD",
    "FRAX",
    "BUSD",
}


def get_bybit_spot_usdt_symbols():
    """
    Fetch the list of tradable Bybit spot pairs quoted in USDT.

    Returns a set like:
    {"BTCUSDT", "ETHUSDT", ...}
    """
    params = {
        "category": "spot",
    }

    try:
        response = requests.get(BYBIT_INSTRUMENTS_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as error:
        print(f"Could not fetch Bybit instruments: {error}")
        return set()

    if data.get("retCode") != 0:
        print(f"Could not fetch Bybit instruments: {data.get('retMsg')}")
        return set()

    instruments = data.get("result", {}).get("list", [])
    if not isinstance(instruments, list) or not instruments:
        print("Bybit returned no instrument list.")
        return set()

    valid_symbols = set()

    for item in instruments:
        symbol = str(item.get("symbol", "")).upper().strip()
        quote_coin = str(item.get("quoteCoin", "")).upper().strip()
        status = str(item.get("status", "")).strip()

        if symbol and quote_coin == "USDT" and status == "Trading":
            valid_symbols.add(symbol)

    return valid_symbols


def get_top_market_cap_symbols():
    """
    Fetch the top coins by market cap from CoinGecko.

    We convert each coin symbol into the Bybit spot symbol format:
    BTC -> BTCUSDT, ETH -> ETHUSDT, etc.

    If CoinGecko fails, return an empty list.
    """
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": TOP_N,
        "page": 1,
        "sparkline": "false",
    }

    try:
        response = requests.get(COINGECKO_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as error:
        print(f"Could not fetch top market cap coins: {error}")
        return []

    if not isinstance(data, list) or not data:
        print("CoinGecko returned no market cap data.")
        return []

    valid_bybit_symbols = get_bybit_spot_usdt_symbols()
    if not valid_bybit_symbols:
        print("Could not build the valid Bybit symbol list.")
        return []

    symbols = []
    seen = set()

    for coin in data:
        base_symbol = str(coin.get("symbol", "")).upper().strip()
        if not base_symbol:
            continue

        if base_symbol in STABLECOINS:
            continue

        bybit_symbol = f"{base_symbol}USDT"
        if bybit_symbol not in valid_bybit_symbols:
            continue

        if bybit_symbol not in seen:
            seen.add(bybit_symbol)
            symbols.append(bybit_symbol)

    return symbols


def get_price_data(symbol):
    """
    Fetch daily close prices from Bybit.

    Returns a DataFrame with:
    - date
    - close

    If the request fails, returns None.
    """
    params = {
        "category": "spot",
        "symbol": symbol,
        "interval": "D",
        "limit": 100,
    }

    try:
        response = requests.get(BYBIT_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as error:
        print(f"Skipping {symbol}: API request failed ({error})")
        return None

    if data.get("retCode") != 0:
        print(f"Skipping {symbol}: Bybit returned an error ({data.get('retMsg')})")
        return None

    candles = data.get("result", {}).get("list", [])
    if not isinstance(candles, list) or not candles:
        print(f"Skipping {symbol}: no data returned")
        return None

    try:
        rows = []
        for candle in candles:
            rows.append(
                {
                    "date": pd.to_datetime(int(candle[0]), unit="ms"),
                    "close": float(candle[4]),
                }
            )
        df = pd.DataFrame(rows)
        df = df.sort_values("date").reset_index(drop=True)
        return df[["date", "close"]]
    except Exception as error:
        print(f"Skipping {symbol}: could not parse data ({error})")
        return None


def compute_return(df, days):
    """
    Compute percentage return over N days.

    Example:
    0.05 means +5%
    """
    if df is None or len(df) < days + 1:
        return None

    try:
        latest_close = df["close"].iloc[-1]
        past_close = df["close"].iloc[-(days + 1)]

        if past_close == 0:
            return None

        return (latest_close / past_close) - 1
    except Exception:
        return None


def build_results():
    """
    Build the relative strength table versus BTC.
    """
    results = []
    symbols = get_top_market_cap_symbols()

    if not symbols:
        print("No top market cap symbols were found.")
        return pd.DataFrame()

    btc_df = get_price_data("BTCUSDT")
    if btc_df is None:
        print("Could not fetch BTC data. No results to build.")
        return pd.DataFrame()

    btc_returns = {}
    for days in LOOKBACKS:
        btc_return = compute_return(btc_df, days)
        if btc_return is None:
            print(f"BTC does not have enough usable data for {days}d return.")
            return pd.DataFrame()
        btc_returns[days] = btc_return

    for symbol in symbols:
        if symbol == "BTCUSDT":
            continue

        df = get_price_data(symbol)
        if df is None:
            continue

        coin_returns = {}
        missing_data = False

        for days in LOOKBACKS:
            coin_return = compute_return(df, days)
            if coin_return is None:
                print(f"Skipping {symbol}: not enough data for {days}d return")
                missing_data = True
                break
            coin_returns[days] = coin_return

        if missing_data:
            continue

        rel_3d = coin_returns[3] - btc_returns[3]
        rel_7d = coin_returns[7] - btc_returns[7]
        rel_30d = coin_returns[30] - btc_returns[30]

        score = 0.2 * rel_3d + 0.3 * rel_7d + 0.5 * rel_30d

        results.append(
            {
                "symbol": symbol,
                "return_3d": coin_returns[3],
                "return_7d": coin_returns[7],
                "return_30d": coin_returns[30],
                "rel_3d": rel_3d,
                "rel_7d": rel_7d,
                "rel_30d": rel_30d,
                "score": score,
                "outperforming_btc": score > 0,
            }
        )

    if not results:
        return pd.DataFrame(
            columns=[
                "symbol",
                "return_3d",
                "return_7d",
                "return_30d",
                "rel_3d",
                "rel_7d",
                "rel_30d",
                "score",
                "outperforming_btc",
            ]
        )

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values("score", ascending=False).reset_index(drop=True)
    return results_df


def main():
    results_df = build_results()

    if results_df.empty:
        print("No valid results were generated.")
        return

    pd.set_option("display.float_format", lambda x: f"{x:.4f}")

    print("\nTop coins by relative strength vs BTC:\n")
    print(results_df.head(10).to_string(index=False))

    try:
        results_df.to_csv(OUTPUT_FILE, index=False)
        print(f"\nFull results saved to {OUTPUT_FILE}")
    except Exception as error:
        print(f"\nCould not save CSV file: {error}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Unexpected error: {error}")
