import streamlit as st
import pandas as pd
from urllib.parse import quote
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Factory Dashboard", layout="wide")

# =================================================================
# CONFIG — all "Lines" (spreadsheets) and their sheet (tab) names
# =================================================================
QC_WORKBOOK_NAME = "3.1 CS VSD 139 inline data 2026"
QC_WORKBOOK_ID = "1DXgUsoKJdNlD6snWjUXi3X8Vn3Dn3Px_KK4Pdsr7No4"

LINES = {
    "Line 1": {
        "id": "1O9J1w32TjgdD9R2shkxBEoqKuEikqpFQEwEwI3rIv6c",
        "tabs": ["L1S1", "L1S2", "L1S3", "L1S4"],
        "type": "standard",
    },
    "Line 2": {
        "id": "1zREY-7nTb_VYCbqXWvy69Prt3g-4VhLUxv66805_loY",
        "tabs": ["L2S1", "L2S2", "L2S3", "L2S4"],
        "type": "standard",
    },
    "Line 3": {
        "id": "1vmJeU3BLhbDp4H_xFlZN9cTVmAnzdDlSAeJCGQdl4vs",
        "tabs": ["L3S1", "L3S2", "L3S3", "L3S4"],
        "type": "standard",
    },
    QC_WORKBOOK_NAME: {
        "id": QC_WORKBOOK_ID,
        "tabs": [
            "OP-2", "OP-3", "OP-4", "OP-5", "OP-6",
            "Shaft & Collar", "Pin & Ecc", "Phosphating",
            "Sheet1", "MTTF of reamer",
        ],
        "type": "qc_workbook",
    },
}

# Column positions (0-indexed) inside the "Shaft & Collar" tab:
# A=0 Date (merged) | B=1 Production time | C=2 (unused) | D=3 Serial No
# E=4 Collar thickness | F=5 Collar runout | G=6 Shaft dia (pos.1)
# H=7 Shaft dia (pos.2) | I=8 Difference between two (~60mm)
# USL/LSL values confirmed directly from the sheet — hardcoded for reliability.
QC_GRAPHS = [
    {"label": "Graph 1 — Collar Thickness", "col": 4, "usl": 7.00, "lsl": 6.80},
    {"label": "Graph 2 — Collar Runout", "col": 5, "usl": 0.03, "lsl": 0.0},
    {"label": "Graph 3 — Shaft Diameter (Col. G)", "col": 6, "usl": 15.9055, "lsl": 15.9005},
    {"label": "Graph 4 — Shaft Diameter (Col. H)", "col": 7, "usl": 15.9055, "lsl": 15.9005},
    {"label": "Graph 5 — Difference Between Two (~60 mm)", "col": 8, "usl": 0.0025, "lsl": 0.0},
]
QC_DATA_START_ROW = 4  # 0-indexed -> Excel row 5


# =================================================================
# SHARED LOADER
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


# =================================================================
# SIDEBAR — Line / Sheet selection
# =================================================================
st.sidebar.title("⚙️ Controls")
line = st.sidebar.selectbox("Select Line", list(LINES.keys()))
sheet = st.sidebar.selectbox("Select Sheet", LINES[line]["tabs"])

if st.sidebar.button("🔄 Refresh data now"):
    st.cache_data.clear()
st.sidebar.caption("Data auto-refreshes from Google Sheets every 5 minutes.")

st.title("📊 Factory Dashboard")
st.subheader(f"{line} — {sheet}")


# =================================================================
# RENDER: STANDARD LINE SHEETS (Line 1 / 2 / 3 — L#S# tabs)
# =================================================================
def clean_line_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    date_col = df.columns[0]
    # Dates like "5/1/2026" or "01 May 2026" -> month/day/year
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce", dayfirst=False)
    df = df.dropna(subset=[date_col])
    for col in df.columns[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def render_standard_sheet(spreadsheet_id: str, sheet_name: str):
    try:
        raw_df = fetch_sheet_csv(spreadsheet_id, sheet_name, header=0)
    except Exception as e:
        st.error(
            f"Could not load data for **{sheet_name}**.\n\n"
            "Check that:\n"
            "1. The tab name matches exactly (case-sensitive).\n"
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
        "Filter by Date (Column A)", value=(min_date, max_date),
        min_value=min_date, max_value=max_date,
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
                          title=f"{sheet_name}: Data Values vs {sr_col}")
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
                        file_name=f"{line.replace(' ', '_')}_{sheet_name}_filtered.csv", mime="text/csv")


# =================================================================
# RENDER: SHAFT & COLLAR QC TAB (5 graphs with USL/LSL)
# =================================================================
def build_qc_dataframe(raw_df: pd.DataFrame) -> pd.DataFrame:
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


def render_qc_shaft_collar(spreadsheet_id: str, sheet_name: str):
    try:
        raw_df = fetch_sheet_csv(spreadsheet_id, sheet_name, header=None)
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
        "Filter by Date", value=(min_date, max_date),
        min_value=min_date, max_value=max_date,
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

        usl, lsl = g["usl"], g["lsl"]
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
# RENDER: OTHER QC WORKBOOK TABS (different layout — raw view for now)
# =================================================================
def render_generic_tab(spreadsheet_id: str, sheet_name: str):
    try:
        raw_df = fetch_sheet_csv(spreadsheet_id, sheet_name, header=None)
    except Exception as e:
        st.error(
            f"Could not load tab **{sheet_name}**.\n\n"
            "Check that the tab name matches exactly and the sheet is shared as "
            f"'Anyone with the link - Viewer'.\n\nTechnical details: {e}"
        )
        st.stop()

    st.info(
        f"'{sheet_name}' uses a different layout (parameters listed row-by-row) than the "
        "standard chart format. Showing the raw data below for now — let me know the exact "
        "row/column structure if you'd like graphs built for this tab too."
    )
    st.dataframe(raw_df, use_container_width=True)

    csv_bytes = raw_df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download raw data as CSV", csv_bytes,
                        file_name=f"{sheet_name.replace(' ', '_')}_raw.csv", mime="text/csv")


# =================================================================
# ROUTING
# =================================================================
line_type = LINES[line]["type"]
spreadsheet_id = LINES[line]["id"]

if line_type == "standard":
    render_standard_sheet(spreadsheet_id, sheet)
elif line_type == "qc_workbook" and sheet == "Shaft & Collar":
    render_qc_shaft_collar(spreadsheet_id, sheet)
else:
    render_generic_tab(spreadsheet_id, sheet)
