import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.graph_objects as go
from itertools import combinations


def get_min_max_date(df, asset, exchange):
    filtered = df[(df["Base"] == asset) & (df["Exchange"] == exchange)]
    min_date = filtered["Date"].min()
    max_date = filtered["Date"].max()
    return min_date, max_date


def process_data(df, asset, exchange_a, exchange_b):
    min_exchange_a, max_exchange_a = get_min_max_date(df, asset, exchange_a)
    min_exchange_b, max_exchange_b = get_min_max_date(df, asset, exchange_b)

    min_date = max(min_exchange_a, min_exchange_b)
    max_date = min(max_exchange_a, max_exchange_b)

    subset = df[
        (df.Date >= min_date)
        & (df.Date <= max_date)
        & (df.Base == asset)
        & ((df.Exchange == exchange_a) | (df.Exchange == exchange_b))
    ]

    daily_sum = (
        subset.groupby(["Base", "Exchange", "Date"])["FundingRate"]
        .sum()
        .reset_index()
        .rename(columns={"FundingRate": "DailyFunding"})
    )

    daily_sum = daily_sum.sort_values(["Base", "Exchange", "Date"])
    daily_sum["CumulativeFunding"] = daily_sum.groupby(["Base", "Exchange"])[
        "DailyFunding"
    ].cumsum()

    merged = daily_sum.merge(daily_sum, on=["Base", "Date"], suffixes=("_a", "_b"))

    pair_df_2025 = merged[merged["Exchange_a"] < merged["Exchange_b"]].copy()
    pair_df_2025["along_bshort"] = (
        pair_df_2025["CumulativeFunding_b"] - pair_df_2025["CumulativeFunding_a"]
    )
    pair_df_2025["blong_ashort"] = (
        pair_df_2025["CumulativeFunding_a"] - pair_df_2025["CumulativeFunding_b"]
    )

    return pair_df_2025[
        (pair_df_2025.Base == asset)
        & (pair_df_2025.Exchange_a == exchange_a)
        & (pair_df_2025.Exchange_b == exchange_b)
    ]


st.markdown(
    """
    <style>
    /* Set background color for the whole app */
    .stApp {
        background-color: black;
        color: white;  /* optional: set default text color to white */
    }

    /* Optional: style sidebar background */
    .css-1d391kg {  /* sidebar container */
        background-color: #111111;
    }

    /* Optional: adjust headings or other elements */
    h1, h2, h3, h4, h5, h6 {
        color: white;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.set_page_config(layout="wide")
st.title("Delta-neutral Funding Rate Arbitrage Explorer")

csv_file_path = "data/funding_rate.csv.gz"


@st.cache_data
def load_data(csv_path):
    df = pd.read_csv(csv_path, compression="gzip")
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], unit="ms")
    df["Timestamp"] = df["Timestamp"].dt.round("5min")
    df["Date"] = df["Timestamp"].dt.floor("D")
    return df


try:
    df = load_data(csv_file_path)
except FileNotFoundError:
    st.error(f"CSV file not found at: {csv_file_path}")
    st.stop()

col1, col2, col3 = st.columns(3)

default_date = pd.to_datetime("2025-01-01")

with col1:
    selected_start_date = st.date_input(
        "Select start date",
        value=default_date,
        min_value=pd.to_datetime("2025-01-01"),
        max_value=pd.to_datetime("2025-12-31"),  # optionally set max date
    )

selected_start_date = pd.Timestamp(selected_start_date)
df_tmp = df[df["Timestamp"] >= pd.Timestamp(selected_start_date)].copy()

query_params = st.query_params

default_asset = "BTC"
base_options = df_tmp["Base"].unique()
sorted_bases = sorted(base_options)
base_default = query_params.get("base", default_asset)


if base_default not in sorted_bases:
    base_default = sorted_bases[0]

with col2:
    asset = st.selectbox(
        "Select Asset", sorted_bases, index=sorted_bases.index(base_default)
    )

filtered_base = df_tmp[df_tmp["Base"] == asset]
exchanges = filtered_base["Exchange"].unique()
exchange_pairs = sorted(combinations(exchanges, 2))

if not exchange_pairs:
    st.warning("No exchange pairs found for selected token.")
    st.stop()

exchange_a_query = query_params.get("exchange_a")
exchange_b_query = query_params.get("exchange_b")
if (
    exchange_a_query != ""
    and exchange_b_query != ""
    and exchange_a_query is not None
    and exchange_b_query is not None
):
    exchange_pair = tuple(sorted((exchange_a_query, exchange_b_query)))

try:
    exchange_pair_index = exchange_pairs.index(exchange_pair)
except:
    exchange_pair_index = 0

with col3:
    exchange_pair = st.selectbox(
        "Select Exchange Pair",
        exchange_pairs,
        format_func=lambda x: f"{x[0]} & {x[1]}",
        index=exchange_pair_index,
    )

exchange_a, exchange_b = exchange_pair

with st.spinner("Loading data..."):
    df_to_display = process_data(df_tmp, asset, exchange_a, exchange_b)

fig = go.Figure()

# Line plots
fig.add_trace(
    go.Scatter(
        x=df_to_display["Date"],
        y=df_to_display["along_bshort"],
        mode="lines+markers",
        name=f"({exchange_a} long, {exchange_b} short) accumulated funding",
        line=dict(color="#1f77b4"),
        marker=dict(color="#1f77b4"),
    )
)
fig.add_trace(
    go.Scatter(
        x=df_to_display["Date"],
        y=df_to_display["blong_ashort"],
        mode="lines+markers",
        name=f"({exchange_b} long, {exchange_a} short) accumulated funding",
        line=dict(color="#ff7f0e"),
        marker=dict(color="#ff7f0e"),
    )
)

# Bar plots (funding rates)
fig.add_trace(
    go.Bar(
        x=df_to_display["Date"],
        y=df_to_display["DailyFunding_a"],
        name=f"({exchange_a}) daily funding",
        opacity=0.5,
        marker_color="#1f77b4",
    )
)
fig.add_trace(
    go.Bar(
        x=df_to_display["Date"],
        y=df_to_display["DailyFunding_b"],
        name=f"({exchange_b}) daily funding",
        opacity=0.5,
        marker_color="#ff7f0e",
    )
)

fig.update_layout(
    title=f"{asset}: {exchange_a} & {exchange_b}",
    yaxis_title="Funding Rate",
    barmode="group",
    hovermode="x unified",
    height=600,
    plot_bgcolor="black",
    paper_bgcolor="black",
    font=dict(color="white"),
    legend=dict(
        orientation="h",  # horizontal legend
        y=1.1,  # position above the plot (1 is top edge, >1 moves higher)
        x=0.5,  # center horizontally
        xanchor="center",
        yanchor="bottom",
    ),
    yaxis=dict(
        tickformat=".6f",
        exponentformat="none",  # Disable scientific notation like 1e-6
        separatethousands=False,
    ),
)

fig.add_annotation(
    x=0.5,
    y=0.5,
    xref="paper",
    yref="paper",
    showarrow=False,
    text="<span style='color:white'>DataMaxi</span><span style='color:yellow'>+</span>",
    font=dict(size=70),
    opacity=0.1,
    xanchor="center",
    yanchor="middle",
)

st.plotly_chart(fig, use_container_width=True)

st.markdown(
    'Data provided by <a href="https://datamaxiplus.com" target="_blank" style="color:#FFFFFF; text-decoration: none;">DataMaxi<span style="color:#F9D342;">+</span></a>',
    unsafe_allow_html=True,
)
