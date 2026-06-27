import streamlit as st
import pandas as pd
from urllib.parse import quote
import plotly.express as px

st.set_page_config(page_title="Production Line Dashboard", layout="wide")

# ---------------------------------------------------------------
# CONFIG — Google Sheet IDs (taken from the links you shared)
# ---------------------------------------------------------------
SHEET_IDS = {
    "Line 1": "1O9J1w32TjgdD9R2shkxBEoqKuEikqpFQEwEwI3rIv6c",
    "Line 2": "1zREY-7nTb_VYCbqXWvy69Prt3g-4VhLUxv66805_loY",
    "Line 3": "1vmJeU3BLhbDp4H_xFlZN9cTVmAnzdDlSAeJCGQdl4vs",
}

# Tab (sheet) names inside each spreadsheet — must match EXACTLY
# (case-sensitive) the tab names in Google Sheets.
SHEET_TABS = {
    "Line 1": ["L1s1", "L1s2", "L1s3", "L1s4"],
    "Line 2": ["L2s1", "L2s2", "L2s3", "L2s4"],
    "Line 3": ["L3s1", "L3s2", "L3s3", "L3s4"],
}

# ---------------------------------------------------------------
# DATA LOADING
# ---------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def load_sheet(spreadsheet_id: str, sheet_name: str) -> pd.DataFrame:
    """
    Pulls a single tab from a public Google Sheet as CSV, using the
    tab NAME (no gid needed). Sheet must be shared as
    'Anyone with the link - Viewer'.
    """
    url = (
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/gviz/tq"
        f"?tqx=out:csv&sheet={quote(sheet_name)}"
    )
    return pd.read_csv(url)


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Cleans column names/types. Assumes:
       col 0 = Date, col 1 = Sr, col 2+ = numeric data values."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    date_col = df.columns[0]
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce", dayfirst=True)
    df = df.dropna(subset=[date_col])

    for col in df.columns[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


# ---------------------------------------------------------------
# SIDEBAR — Line / Sheet selection
# ---------------------------------------------------------------
st.sidebar.title("⚙️ Controls")

line = st.sidebar.selectbox("Select Line", list(SHEET_IDS.keys()))
sheet = st.sidebar.selectbox("Select Sheet", SHEET_TABS[line])

if st.sidebar.button("🔄 Refresh data now"):
    st.cache_data.clear()

st.sidebar.caption("Data auto-refreshes from Google Sheets every 5 minutes.")

# ---------------------------------------------------------------
# LOAD + VALIDATE
# ---------------------------------------------------------------
st.title("📊 Production Line Dashboard")
st.subheader(f"{line} — {sheet}")

try:
    raw_df = load_sheet(SHEET_IDS[line], sheet)
except Exception as e:
    st.error(
        f"Could not load data for **{line} / {sheet}**.\n\n"
        "Check that:\n"
        "1. The tab name in Google Sheets matches exactly (case-sensitive).\n"
        "2. The sheet is shared as 'Anyone with the link - Viewer'.\n\n"
        f"Technical details: {e}"
    )
    st.stop()

if raw_df.empty:
    st.warning("No data found in this sheet tab.")
    st.stop()

df = clean_dataframe(raw_df)

if df.empty:
    st.warning("No valid rows found after parsing the Date column (Column A).")
    st.stop()

date_col = df.columns[0]      # Column A
sr_col = df.columns[1]        # Column B
value_cols = list(df.columns[2:])   # Remaining data columns

# ---------------------------------------------------------------
# SIDEBAR — Date filter + column selection
# ---------------------------------------------------------------
min_date = df[date_col].min().date()
max_date = df[date_col].max().date()

st.sidebar.markdown("---")
date_range = st.sidebar.date_input(
    "Filter by Date (Column A)",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
)

selected_cols = st.sidebar.multiselect(
    "Data columns to plot",
    options=value_cols,
    default=value_cols,
)

if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date = end_date = date_range

mask = (df[date_col].dt.date >= start_date) & (df[date_col].dt.date <= end_date)
filtered = df.loc[mask].sort_values(by=sr_col)

st.caption(f"Showing **{len(filtered)}** rows from **{start_date}** to **{end_date}**")

# ---------------------------------------------------------------
# CHART + METRICS
# ---------------------------------------------------------------
col_chart, col_metrics = st.columns([3, 1])

with col_chart:
    if not selected_cols:
        st.info("Select at least one data column from the sidebar to plot.")
    elif filtered.empty:
        st.info("No rows in the selected date range.")
    else:
        plot_df = filtered.melt(
            id_vars=[sr_col],
            value_vars=selected_cols,
            var_name="Metric",
            value_name="Value",
        )
        fig = px.line(
            plot_df,
            x=sr_col,
            y="Value",
            color="Metric",
            markers=True,
            title=f"{sheet}: Data Values vs {sr_col}",
        )
        fig.update_layout(
            xaxis_title=sr_col,
            yaxis_title="Value",
            legend_title_text="Metric",
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

with col_metrics:
    st.metric("Rows in view", len(filtered))
    for c in selected_cols:
        vals = filtered[c].dropna()
        st.metric(f"Avg {c}", round(vals.mean(), 2) if not vals.empty else "—")

# ---------------------------------------------------------------
# RAW DATA + DOWNLOAD
# ---------------------------------------------------------------
with st.expander("📋 View filtered raw data"):
    st.dataframe(filtered, use_container_width=True)

csv_bytes = filtered.to_csv(index=False).encode("utf-8")
st.download_button(
    "⬇️ Download filtered data as CSV",
    data=csv_bytes,
    file_name=f"{line.replace(' ', '_')}_{sheet}_filtered.csv",
    mime="text/csv",
)
