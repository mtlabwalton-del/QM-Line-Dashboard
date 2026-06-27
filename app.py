import streamlit as st
import pandas as pd
from urllib.parse import quote
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Factory Dashboard", layout="wide")

# =================================================================
# CONFIG
# =================================================================
LINE_SHEET_IDS = {
    "Line 1": "1O9J1w32TjgdD9R2shkxBEoqKuEikqpFQEwEwI3rIv6c",
    "Line 2": "1zREY-7nTb_VYCbqXWvy69Prt3g-4VhLUxv66805_loY",
    "Line 3": "1vmJeU3BLhbDp4H_xFlZN9cTVmAnzdDlSAeJCGQdl4vs",
}

# Tab names exactly as they appear in Google Sheets (ALL CAPS "S")
LINE_SHEET_TABS = {
    "Line 1": ["L1S1", "L1S2", "L1S3", "L1S4"],
    "Line 2": ["L2S1", "L2S2", "L2S3", "L2S4"],
    "Line 3": ["L3S1", "L3S2", "L3S3", "L3S4"],
}

QC_SPREADSHEET_ID = "1DXgUsoKJdNlD6snWjUXi3X8Vn3Dn3Px_KK4Pdsr7No4"
QC_SHEET_NAME = "Shaft & Collar"

# Column positions (0-indexed) inside the "Shaft & Collar" tab:
# A=0 Date (merged) | B=1 Production time | C=2 (unused) | D=3 Serial No
# E=4 Collar thickness | F=5 Collar runout | G=6 Shaft dia (pos.1)
# H=7 Shaft dia (pos.2) | I=8 fifth measurement (USL only)
QC_GRAPHS = [
    {"label": "Graph 1 — Collar Thickness", "col": 4, "usl_row": 2, "lsl_row": 3, "spec_col": 4},
    {"label": "Graph 2 — Collar Runout", "col": 5, "usl_row": 2, "lsl_row": 3, "spec_col": 5},
    {"label": "Graph 3 — Shaft Diameter (Col. G)", "col": 6, "usl_row": 2, "lsl_row": 3, "spec_col": 6},
    {"label": "Graph 4 — Shaft Diameter (Col. H)", "col": 7, "usl_row": 2, "lsl_row": 3, "spec_col": 6},
    {"label": "Graph 5 — Column I Measurement", "col": 8, "usl_row": 2, "lsl_row": None, "spec_col": 8},
]
# Row 1 (index 0) = Date | Row 2 (index 1) = blank/header | Row 3 (index 2) = USL
# Row 4 (index 3) = LSL | Row 5 (index 4) onward = data
QC_DATA_START_ROW = 4  # 0-indexed -> Excel row 5


# =================================================================
# SHARED LOADERS
# =================================================================
@st.cache_data(ttl=300, show_spinner=False)
def fetch_sheet_csv(spreadsheet_id: str, sheet_name: str, header) -> pd.DataFrame:
    """Pulls one tab from a public Google Sheet as CSV by tab NAME.
       Sheet must be shared as 'Anyone with the link - Viewer'."""
    url = (
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/gviz/tq"
        f"?tqx=out:csv&sheet={quote(sheet_name)}"
    )
    return pd.read_csv(url, header=header)


def get_spec_value(raw_df: pd.DataFrame, row_idx, col_idx: int):
    """Safely reads a single spec (USL/LSL) cell from the raw sheet."""
    if row_idx is None:
        return None
    try:
        val = raw_df.iloc[row_idx, col_idx]
        return float(val)
    except Exception:
        return None


# =================================================================
# SIDEBAR — top-level dashboard chooser
# =================================================================
st.sidebar.title("⚙️ Dashboard")
dashboard = st.sidebar.radio(
    "Choose a dashboard",
    ["🏭 Production Lines", "🔧 Shaft & Collar QC"],
)

if st.sidebar.button("🔄 Refresh data now"):
    st.cache_data.clear()
st.sidebar.caption("Data auto-refreshes from Google Sheets every 5 minutes.")


# =================================================================
# DASHBOARD 1 — PRODUCTION LINES (Line 1 / 2 / 3)
# =================================================================
def clean_line_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    date_col = df.columns[0]
    # Dates like "5/1/2026" or "01 May 2026" -> month/day/year (dayfirst=False)
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce", dayfirst=False)
    df = df.dropna(subset=[date_col])
    for col in df.columns[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def render_line_dashboard():
    st.title("📊 Production Line Dashboard")

    st.sidebar.markdown("---")
    line = st.sidebar.selectbox("Select Line", list(LINE_SHEET_IDS.keys()))
    sheet = st.sidebar.selectbox("Select Sheet", LINE_SHEET_TABS[line])

    st.subheader(f"{line} — {sheet}")

    try:
        raw_df = fetch_sheet_csv(LINE_SHEET_IDS[line], sheet, header=0)
    except Exception as e:
        st.error(
            f"Could not load data for **{line} / {sheet}**.\n\n"
            "Check that:\n"
            "1. The tab name matches exactly (e.g. `L1S1`, capital S).\n"
            "2. The sheet is shared as 'Anyone with the link - Viewer'.\n\n"
            f"Technical details: {e}"
        )
        st.stop()

    if raw_df.empty:
        st.warning("No data found in this sheet tab.")
        st.stop()

    df = clean_line_dataframe(raw_df)
    if df.empty:
        st.warning("No valid rows found after parsing the Date column (Column A).")
        st.stop()

    date_col, sr_col = df.columns[0], df.columns[1]
    value_cols = list(df.columns[2:])

    min_date, max_date = df[date_col].min().date(), df[date_col].max().date()

    st.sidebar.markdown("---")
    date_range = st.sidebar.date_input(
        "Filter by Date (Column A)",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    selected_cols = st.sidebar.multiselect("Data columns to plot", value_cols, default=value_cols)

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date = end_date = date_range

    mask = (df[date_col].dt.date >= start_date) & (df[date_col].dt.date <= end_date)
    filtered = df.loc[mask].sort_values(by=sr_col)

    st.caption(f"Showing **{len(filtered)}** rows from **{start_date}** to **{end_date}**")

    col_chart, col_metrics = st.columns([3, 1])
    with col_chart:
        if not selected_cols:
            st.info("Select at least one data column from the sidebar to plot.")
        elif filtered.empty:
            st.info("No rows in the selected date range.")
        else:
            plot_df = filtered.melt(id_vars=[sr_col], value_vars=selected_cols,
                                     var_name="Metric", value_name="Value")
            fig = px.line(plot_df, x=sr_col, y="Value", color="Metric", markers=True,
                          title=f"{sheet}: Data Values vs {sr_col}")
            fig.update_layout(xaxis_title=sr_col, yaxis_title="Value", hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

    with col_metrics:
        st.metric("Rows in view", len(filtered))
        for c in selected_cols:
            vals = filtered[c].dropna()
            st.metric(f"Avg {c}", round(vals.mean(), 2) if not vals.empty else "—")

    with st.expander("📋 View filtered raw data"):
        st.dataframe(filtered, use_container_width=True)

    csv_bytes = filtered.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download filtered data as CSV", csv_bytes,
                        file_name=f"{line.replace(' ', '_')}_{sheet}_filtered.csv", mime="text/csv")


# =================================================================
# DASHBOARD 2 — SHAFT & COLLAR QC
# =================================================================
def build_qc_dataframe(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Builds a tidy dataframe from the raw 'Shaft & Collar' sheet:
       - forward-fills the merged Date cells in column A
       - keeps Production time (col B) and Serial No (col D)
       - keeps the 5 measurement columns (E,F,G,H,I)
    """
    raw = raw_df.copy()
    raw[0] = raw[0].ffill()  # un-merge Date column

    data = raw.iloc[QC_DATA_START_ROW:].copy()
    data = data.rename(columns={0: "Date", 1: "ProdTime", 3: "Serial"})

    data["Date"] = pd.to_datetime(data["Date"], errors="coerce", dayfirst=False)
    data["Serial"] = pd.to_numeric(data["Serial"], errors="coerce")
    data = data.dropna(subset=["Serial"])

    for g in QC_GRAPHS:
        data[g["col"]] = pd.to_numeric(data[g["col"]], errors="coerce")

    return data


def render_qc_dashboard():
    st.title("🔧 Shaft & Collar QC Dashboard")
    st.caption("Source: 3.1 CS VSD 139 inline data 2026 — tab: 'Shaft & Collar'")

    try:
        raw_df = fetch_sheet_csv(QC_SPREADSHEET_ID, QC_SHEET_NAME, header=None)
    except Exception as e:
        st.error(
            "Could not load the 'Shaft & Collar' tab.\n\n"
            "Check that the tab name matches exactly and the sheet is shared as "
            f"'Anyone with the link - Viewer'.\n\nTechnical details: {e}"
        )
        st.stop()

    data = build_qc_dataframe(raw_df)
    if data.empty:
        st.warning("No data rows found (check QC_DATA_START_ROW / column mapping).")
        st.stop()

    min_date, max_date = data["Date"].min().date(), data["Date"].max().date()

    st.sidebar.markdown("---")
    date_range = st.sidebar.date_input(
        "Filter by Date",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    graph_labels = [g["label"] for g in QC_GRAPHS]
    selected_graphs = st.sidebar.multiselect("Graphs to show", graph_labels, default=graph_labels)

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date = end_date = date_range

    mask = (data["Date"].dt.date >= start_date) & (data["Date"].dt.date <= end_date)
    filtered = data.loc[mask].sort_values(by="Serial")

    st.caption(f"Showing **{len(filtered)}** rows from **{start_date}** to **{end_date}**")

    for g in QC_GRAPHS:
        if g["label"] not in selected_graphs:
            continue

        usl = get_spec_value(raw_df, g["usl_row"], g["spec_col"])
        lsl = get_spec_value(raw_df, g["lsl_row"], g["spec_col"]) if g["lsl_row"] is not None else None

        plot_data = filtered[["Serial", "ProdTime", "Date", g["col"]]].dropna(subset=[g["col"]])

        st.subheader(g["label"])
        if plot_data.empty:
            st.info("No data points for this measurement in the selected date range.")
            continue

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=plot_data["Serial"], y=plot_data[g["col"]],
            mode="lines+markers", name="Measured value",
            customdata=plot_data[["ProdTime", "Date"]].astype(str),
            hovertemplate="Serial: %{x}<br>Value: %{y}<br>Time: %{customdata[0]}<br>Date: %{customdata[1]}<extra></extra>",
        ))
        if usl is not None:
            fig.add_hline(y=usl, line_dash="dash", line_color="red",
                          annotation_text=f"USL = {usl}", annotation_position="top right")
        if lsl is not None:
            fig.add_hline(y=lsl, line_dash="dash", line_color="orange",
                          annotation_text=f"LSL = {lsl}", annotation_position="bottom right")

        fig.update_layout(xaxis_title="Serial No.", yaxis_title="Measured value", hovermode="closest")
        st.plotly_chart(fig, use_container_width=True)

        col1, col2, col3 = st.columns(3)
        col1.metric("Avg", round(plot_data[g["col"]].mean(), 4))
        col1.metric("Std Dev", round(plot_data[g["col"]].std(), 4))
        if usl is not None:
            col2.metric("Above USL", int((plot_data[g["col"]] > usl).sum()))
        if lsl is not None:
            col3.metric("Below LSL", int((plot_data[g["col"]] < lsl).sum()))

    with st.expander("📋 View filtered raw data (all measurements)"):
        cols_to_show = ["Date", "ProdTime", "Serial"] + [g["col"] for g in QC_GRAPHS]
        st.dataframe(filtered[cols_to_show], use_container_width=True)

    csv_bytes = filtered.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download filtered data as CSV", csv_bytes,
                        file_name="Shaft_Collar_filtered.csv", mime="text/csv")


# =================================================================
# ROUTING
# =================================================================
if dashboard == "🏭 Production Lines":
    render_line_dashboard()
else:
    render_qc_dashboard()
