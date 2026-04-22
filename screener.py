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
COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets"
REQUEST_HEADERS = {
    "User-Agent": "crypto-relative-strength-screener/1.0",
    "Accept": "application/json",
}
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


def get_market_data():
    """
    Fetch the top market cap coins from CoinGecko in one request.

    We ask for:
    - top coins by market cap
    - 7d sparkline data
    - 7d and 30d percentage change

    This keeps the app lightweight and avoids making one request per coin.
    """
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": TOP_N,
        "page": 1,
        "sparkline": "true",
        "price_change_percentage": "7d,30d",
    }

    try:
        response = requests.get(
            COINGECKO_URL,
            params=params,
            headers=REQUEST_HEADERS,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as error:
        print(f"Could not fetch market data from CoinGecko: {error}")
        return []

    if not isinstance(data, list) or not data:
        print("CoinGecko returned no market data.")
        return []

    return data


def get_price_data(symbol):
    """
    Kept for compatibility with the original script structure.

    This version builds a small DataFrame from the 7d sparkline data.
    It is mainly useful for estimating the 3d return.
    """
    market_data = get_market_data()

    for coin in market_data:
        coin_symbol = str(coin.get("symbol", "")).upper().strip()
        if f"{coin_symbol}USDT" != symbol:
            continue

        prices = coin.get("sparkline_in_7d", {}).get("price", [])
        if not prices:
            return None

        try:
            rows = []
            for index, price in enumerate(prices):
                rows.append(
                    {
                        "date": index,
                        "close": float(price),
                    }
                )
            return pd.DataFrame(rows)
        except Exception as error:
            print(f"Skipping {symbol}: could not parse sparkline data ({error})")
            return None

    return None


def compute_return(df, days):
    """
    Compute percentage return over N days from a DataFrame.

    This is still used for the 3d return approximation based on the 7d sparkline.
    """
    if df is None or df.empty:
        return None

    try:
        total_points = len(df)
        if total_points < 2:
            return None

        latest_close = df["close"].iloc[-1]
        target_index = round((total_points - 1) * (days / 7))
        past_position = max(0, (total_points - 1) - target_index)
        past_close = df["close"].iloc[past_position]

        if past_close == 0:
            return None

        return (latest_close / past_close) - 1
    except Exception:
        return None


def build_results():
    """
    Build the relative strength table versus BTC.

    Logic:
    - top 50 by market cap from CoinGecko
    - exclude stablecoins
    - use CoinGecko 7d and 30d percentage changes directly
    - estimate 3d return from the 7d sparkline
    """
    market_data = get_market_data()
    if not market_data:
        print("No market data was found.")
        return pd.DataFrame()

    filtered_coins = []
    for coin in market_data:
        symbol = str(coin.get("symbol", "")).upper().strip()
        if not symbol:
            continue
        if symbol in STABLECOINS:
            continue
        filtered_coins.append(coin)

    btc_coin = None
    for coin in filtered_coins:
        if str(coin.get("symbol", "")).upper().strip() == "BTC":
            btc_coin = coin
            break

    if btc_coin is None:
        print("BTC was not found in the market data.")
        return pd.DataFrame()

    btc_df = pd.DataFrame(
        {
            "date": range(len(btc_coin.get("sparkline_in_7d", {}).get("price", []))),
            "close": btc_coin.get("sparkline_in_7d", {}).get("price", []),
        }
    )

    btc_return_3d = compute_return(btc_df, 3)
    btc_return_7d = btc_coin.get("price_change_percentage_7d_in_currency")
    btc_return_30d = btc_coin.get("price_change_percentage_30d_in_currency")

    if btc_return_3d is None or btc_return_7d is None or btc_return_30d is None:
        print("BTC does not have enough usable data.")
        return pd.DataFrame()

    btc_return_7d = btc_return_7d / 100
    btc_return_30d = btc_return_30d / 100

    results = []

    for coin in filtered_coins:
        symbol = str(coin.get("symbol", "")).upper().strip()
        if symbol == "BTC":
            continue

        sparkline_prices = coin.get("sparkline_in_7d", {}).get("price", [])
        if not sparkline_prices:
            print(f"Skipping {symbol}USDT: no sparkline data returned")
            continue

        coin_df = pd.DataFrame(
            {
                "date": range(len(sparkline_prices)),
                "close": sparkline_prices,
            }
        )

        return_3d = compute_return(coin_df, 3)
        return_7d = coin.get("price_change_percentage_7d_in_currency")
        return_30d = coin.get("price_change_percentage_30d_in_currency")

        if return_3d is None or return_7d is None or return_30d is None:
            print(f"Skipping {symbol}USDT: missing return data")
            continue

        return_7d = return_7d / 100
        return_30d = return_30d / 100

        rel_3d = return_3d - btc_return_3d
        rel_7d = return_7d - btc_return_7d
        rel_30d = return_30d - btc_return_30d

        score = 0.2 * rel_3d + 0.3 * rel_7d + 0.5 * rel_30d

        results.append(
            {
                "symbol": f"{symbol}USDT",
                "return_3d": return_3d,
                "return_7d": return_7d,
                "return_30d": return_30d,
                "rel_3d": rel_3d,
                "rel_7d": rel_7d,
                "rel_30d": rel_30d,
                "score": score,
                "outperforming_btc": score > 0,
            }
        )

    if not results:
        print("No valid screener results were generated.")
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
