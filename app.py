from datetime import datetime

import pandas as pd
import streamlit as st

from screener import build_results


st.set_page_config(page_title="Crypto Relative Strength Screener", layout="wide")


def color_value(value):
    """
    Color positive numbers green and negative numbers red.
    """
    if isinstance(value, bool):
        return ""

    if isinstance(value, (int, float)):
        if value > 0:
            return "color: green;"
        if value < 0:
            return "color: red;"

    return ""


def main():
    st.title("Crypto Relative Strength Screener")

    st.write("This app shows which coins are outperforming BTC based on the existing screener logic.")

    if st.button("Refresh data"):
        st.rerun()

    csv_file = "crypto_relative_strength.csv"
    results_df = build_results()
    data_source = "Live API data"

    if not results_df.empty:
        try:
            results_df.to_csv(csv_file, index=False)
        except Exception:
            pass
    elif pd.io.common.file_exists(csv_file):
        results_df = pd.read_csv(csv_file)
        data_source = "Saved CSV fallback"
        st.warning("Live market data could not be loaded. Showing the last saved results instead.")
    else:
        st.error("No valid results were generated.")
        return

    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    st.caption(f"Data source: {data_source}")

    show_only_outperforming = st.checkbox("Show only outperforming BTC", value=False)
    min_score = st.slider("Minimum score", min_value=-0.50, max_value=0.50, value=-0.50, step=0.01)

    filtered_df = results_df.copy()

    if show_only_outperforming:
        filtered_df = filtered_df[filtered_df["outperforming_btc"]]

    filtered_df = filtered_df[filtered_df["score"] >= min_score]
    filtered_df = filtered_df.sort_values("score", ascending=False).reset_index(drop=True)

    st.subheader("Top 5 Coins")
    st.dataframe(
        filtered_df.head(5).style.map(color_value),
        width='stretch',
    )

    st.subheader("Score Chart")
    chart_df = filtered_df.set_index("symbol")[["score"]]
    st.bar_chart(chart_df)

    st.subheader("Full Results")
    st.dataframe(
        filtered_df.style.map(color_value),
        width='stretch',
    )

    st.write(f"Total coins shown: {len(filtered_df)}")


if __name__ == "__main__":
    main()
