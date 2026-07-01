import streamlit as st
import pandas as pd
from urllib.parse import quote
import plotly.express as px
import plotly.graph_objects as go
import os

st.set_page_config(page_title="Factory Dashboard", layout="wide")

# =================================================================
# CONFIG — All Lines (Google Sheets + Local Excel)
# =================================================================

QC_WORKBOOK_NAME = "3.1 CS VSD 139 inline data 2026"
QC_WORKBOOK_ID   = "1DXgUsoKJdNlD6snWjUXi3X8Vn3Dn3Px_KK4Pdsr7No4"

# Path to local Excel file (relative to app.py — file must be in data/ folder in the repo)
EXCEL_LINE_NAME = "Input Data - Crankcase Master Metal VSD Long Leg"
EXCEL_FILE_PATH = os.path.join("data", "Input Data - Crankcase Master Metal VSD Long Leg.xlsx")

LINES = {
    "Line 1": {
        "id":   "1O9J1w32TjgdD9R2shkxBEoqKuEikqpFQEwEwI3rIv6c",
        "tabs": ["L1S1", "L1S2", "L1S3", "L1S4"],
        "type": "standard",
    },
    "Line 2": {
        "id":   "1zREY-7nTb_VYCbqXWvy69Prt3g-4VhLUxv66805_loY",
        "tabs": ["L2S1", "L2S2", "L2S3", "L2S4"],
        "type": "standard",
    },
    "Line 3": {
        "id":   "1vmJeU3BLhbDp4H_xFlZN9cTVmAnzdDlSAeJCGQdl4vs",
        "tabs": ["L3S1", "L3S2", "L3S3", "L3S4"],
        "type": "standard",
    },
    QC_WORKBOOK_NAME: {
        "id":   QC_WORKBOOK_ID,
        "tabs": [
            "OP-2", "OP-3", "OP-4", "OP-5", "OP-6",
            "Shaft & Collar", "Pin & Ecc", "Phosphating",
            "Sheet1", "MTTF of reamer",
        ],
        "type": "qc_workbook",
    },
    EXCEL_LINE_NAME: {
        "id":   EXCEL_FILE_PATH,   # reusing id field to store file path
        "tabs": [],                 # dynamically loaded from the Excel file
        "type": "excel_local",
    },
}

# ---------------------------------------------------------------
# Shaft & Collar QC graph specs (hardcoded — confirmed values)
# ---------------------------------------------------------------
QC_GRAPHS = [
    {"label": "Graph 1 — Collar Thickness",             "col": 4, "usl": 7.00,     "lsl": 6.80},
    {"label": "Graph 2 — Collar Runout",                "col": 5, "usl": 0.03,     "lsl": 0.0},
    {"label": "Graph 3 — Shaft Diameter (Col. G)",      "col": 6, "usl": 15.9055,  "lsl": 15.9005},
    {"label": "Graph 4 — Shaft Diameter (Col. H)",      "col": 7, "usl": 15.9055,  "lsl": 15.9005},
    {"label": "Graph 5 — Difference Between Two (~60mm)","col": 8, "usl": 0.0025,  "lsl": 0.0},
]
QC_DATA_START_ROW = 4   # 0-indexed → Excel row 5


# =================================================================
# LOADERS
# =================================================================
@st.cache_data(ttl=300, show_spinner=False)
def fetch_sheet_csv(spreadsheet_id: str, sheet_name: str, header) -> pd.DataFrame:
    """Pulls one tab from a public Google Sheet as CSV."""
    url = (
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/gviz/tq"
        f"?tqx=out:csv&sheet={quote(sheet_name)}"
    )
    return pd.read_csv(url, header=header)


@st.cache_data(ttl=60, show_spinner=False)
def load_excel_sheet_names(file_path: str):
    """Returns list of sheet names from a local Excel file."""
    xl = pd.ExcelFile(file_path, engine="openpyxl")
    return xl.sheet_names


@st.cache_data(ttl=60, show_spinner=False)
def load_excel_sheet(file_path: str, sheet_name: str) -> pd.DataFrame:
    """Loads one sheet from a local Excel file."""
    return pd.read_excel(file_path, sheet_name=sheet_name, engine="openpyxl")


# =================================================================
# SIDEBAR — Line / Sheet selection
# =================================================================
st.sidebar.title("⚙️ Controls")

# Dynamically read Excel sheet names so the sidebar stays accurate
excel_tabs_loaded = []
excel_available = os.path.exists(EXCEL_FILE_PATH)
if excel_available:
    try:
        excel_tabs_loaded = load_excel_sheet_names(EXCEL_FILE_PATH)
        LINES[EXCEL_LINE_NAME]["tabs"] = excel_tabs_loaded
    except Exception:
        pass

line = st.sidebar.selectbox("Select Line", list(LINES.keys()))

available_tabs = LINES[line]["tabs"]
if not available_tabs:
    st.sidebar.warning("No sheets found for this line.")
    st.stop()

sheet = st.sidebar.selectbox("Select Sheet", available_tabs)

if st.sidebar.button("🔄 Refresh data now"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.caption("Google Sheet data auto-refreshes every 5 min. Excel data refreshes every 1 min.")

st.title("📊 Factory Dashboard")
st.subheader(f"{line}  ›  {sheet}")


# =================================================================
# DATE PARSING HELPER
# =================================================================
def parse_dates(series: pd.Series) -> pd.Series:
    """Handles mixed date formats: '5/1/2026', '01 May 2026', etc."""
    return pd.to_datetime(series, errors="coerce", dayfirst=False)


# =================================================================
# RENDER 1 — STANDARD LINE SHEETS (Line 1 / 2 / 3)
# =================================================================
def clean_line_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    date_col = df.columns[0]
    df[date_col] = parse_dates(df[date_col])
    df = df.dropna(subset=[date_col])
    for col in df.columns[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def render_standard_sheet(spreadsheet_id: str, sheet_name: str, line_name: str):
    try:
        raw_df = fetch_sheet_csv(spreadsheet_id, sheet_name, header=0)
    except Exception as e:
        st.error(f"Could not load **{sheet_name}**.\n\nTechnical details: {e}")
        st.stop()

    if raw_df.empty:
        st.warning("No data found in this sheet tab.")
        st.stop()

    df = clean_line_df(raw_df)
    if df.empty:
        st.warning("No valid rows found after parsing the Date column.")
        st.stop()

    date_col, sr_col = df.columns[0], df.columns[1]
    value_cols = list(df.columns[2:])
    min_date, max_date = df[date_col].min().date(), df[date_col].max().date()

    st.sidebar.markdown("---")
    date_range = st.sidebar.date_input(
        "Filter by Date", value=(min_date, max_date),
        min_value=min_date, max_value=max_date,
    )
    selected_cols = st.sidebar.multiselect("Columns to plot", value_cols, default=value_cols)

    start_date, end_date = (date_range if isinstance(date_range, tuple) and len(date_range) == 2
                             else (date_range, date_range))

    mask = (df[date_col].dt.date >= start_date) & (df[date_col].dt.date <= end_date)
    filtered = df.loc[mask].sort_values(by=sr_col)
    st.caption(f"Showing **{len(filtered)}** rows  |  {start_date} → {end_date}")

    col_chart, col_metrics = st.columns([3, 1])
    with col_chart:
        if not selected_cols:
            st.info("Select at least one column from the sidebar to plot.")
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

    with st.expander("📋 Raw data"):
        st.dataframe(filtered, use_container_width=True)

    st.download_button(
        "⬇️ Download CSV", filtered.to_csv(index=False).encode(),
        file_name=f"{line_name.replace(' ','_')}_{sheet_name}_filtered.csv", mime="text/csv",
    )


# =================================================================
# RENDER 2 — SHAFT & COLLAR QC GRAPHS
# =================================================================
def build_qc_df(raw_df: pd.DataFrame) -> pd.DataFrame:
    raw = raw_df.copy()
    raw[0] = raw[0].ffill()
    data = raw.iloc[QC_DATA_START_ROW:].copy()
    data = data.rename(columns={0: "Date", 1: "ProdTime", 3: "Serial"})
    data["Date"] = parse_dates(data["Date"])
    data["Serial"] = pd.to_numeric(data["Serial"], errors="coerce")
    data = data.dropna(subset=["Serial"])
    for g in QC_GRAPHS:
        data[g["col"]] = pd.to_numeric(data[g["col"]], errors="coerce")
    return data


def render_qc_shaft_collar(spreadsheet_id: str, sheet_name: str):
    try:
        raw_df = fetch_sheet_csv(spreadsheet_id, sheet_name, header=None)
    except Exception as e:
        st.error(f"Could not load **{sheet_name}**.\n\nTechnical details: {e}")
        st.stop()

    data = build_qc_df(raw_df)
    if data.empty:
        st.warning("No data rows found.")
        st.stop()

    min_date, max_date = data["Date"].min().date(), data["Date"].max().date()

    st.sidebar.markdown("---")
    date_range = st.sidebar.date_input(
        "Filter by Date", value=(min_date, max_date),
        min_value=min_date, max_value=max_date,
    )
    selected_graphs = st.sidebar.multiselect(
        "Graphs to show", [g["label"] for g in QC_GRAPHS],
        default=[g["label"] for g in QC_GRAPHS],
    )

    start_date, end_date = (date_range if isinstance(date_range, tuple) and len(date_range) == 2
                             else (date_range, date_range))

    mask = (data["Date"].dt.date >= start_date) & (data["Date"].dt.date <= end_date)
    filtered = data.loc[mask].sort_values(by="Serial")
    st.caption(f"Showing **{len(filtered)}** rows  |  {start_date} → {end_date}")

    for g in QC_GRAPHS:
        if g["label"] not in selected_graphs:
            continue
        plot_data = filtered[["Serial", "ProdTime", "Date", g["col"]]].dropna(subset=[g["col"]])

        st.subheader(g["label"])
        st.caption(f"USL = {g['usl']}   |   LSL = {g['lsl']}")

        if plot_data.empty:
            st.info("No data points in the selected date range.")
            continue

        fig = go.Figure()
        # Colour points red if outside spec, green if inside
        colors = plot_data[g["col"]].apply(
            lambda v: "red" if (v > g["usl"] or v < g["lsl"]) else "steelblue"
        )
        fig.add_trace(go.Scatter(
            x=plot_data["Serial"], y=plot_data[g["col"]],
            mode="lines+markers",
            marker=dict(color=colors, size=7),
            line=dict(color="steelblue"),
            name="Measured",
            customdata=plot_data[["ProdTime", "Date"]].astype(str),
            hovertemplate=(
                "Serial: %{x}<br>Value: %{y}<br>"
                "Time: %{customdata[0]}<br>Date: %{customdata[1]}<extra></extra>"
            ),
        ))
        fig.add_hline(y=g["usl"], line_dash="dash", line_color="red",
                      annotation_text=f"USL = {g['usl']}", annotation_position="top right")
        fig.add_hline(y=g["lsl"], line_dash="dash", line_color="orange",
                      annotation_text=f"LSL = {g['lsl']}", annotation_position="bottom right")
        fig.update_layout(xaxis_title="Serial No.", yaxis_title="Value", hovermode="closest")
        st.plotly_chart(fig, use_container_width=True)

        c1, c2, c3 = st.columns(3)
        vals = plot_data[g["col"]]
        c1.metric("Avg",     round(vals.mean(), 4))
        c1.metric("Std Dev", round(vals.std(),  4))
        c2.metric("Above USL", int((vals > g["usl"]).sum()))
        c3.metric("Below LSL", int((vals < g["lsl"]).sum()))

    with st.expander("📋 Raw data"):
        cols_to_show = ["Date", "ProdTime", "Serial"] + [g["col"] for g in QC_GRAPHS]
        st.dataframe(filtered[cols_to_show], use_container_width=True)

    st.download_button(
        "⬇️ Download CSV", filtered.to_csv(index=False).encode(),
        file_name="Shaft_Collar_filtered.csv", mime="text/csv",
    )


# =================================================================
# RENDER 3 — LOCAL EXCEL FILE (any sheet tab)
# =================================================================
def render_excel_sheet(file_path: str, sheet_name: str):
    if not os.path.exists(file_path):
        st.error(
            f"Excel file not found at **`{file_path}`**.\n\n"
            "Make sure you:\n"
            "1. Created a `data/` folder inside your GitHub repo.\n"
            "2. Copied the Excel file there and pushed to GitHub.\n"
            "3. The filename matches exactly (including spaces and `.xlsx`)."
        )
        st.stop()

    try:
        raw_df = load_excel_sheet(file_path, sheet_name)
    except Exception as e:
        st.error(f"Could not read sheet **{sheet_name}** from Excel.\n\nDetails: {e}")
        st.stop()

    if raw_df.empty:
        st.warning("No data found in this sheet.")
        st.stop()

    # --- Clean: col 0 = Date, col 1 = Sr/ID, col 2+ = values ---
    df = raw_df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    date_col = df.columns[0]
    sr_col   = df.columns[1]

    df[date_col] = parse_dates(df[date_col])
    df = df.dropna(subset=[date_col])
    for col in df.columns[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if df.empty:
        st.warning("No valid rows found after parsing the Date column.")
        st.stop()

    value_cols = list(df.columns[2:])
    min_date, max_date = df[date_col].min().date(), df[date_col].max().date()

    st.sidebar.markdown("---")
    date_range = st.sidebar.date_input(
        "Filter by Date", value=(min_date, max_date),
        min_value=min_date, max_value=max_date,
    )
    selected_cols = st.sidebar.multiselect("Columns to plot", value_cols, default=value_cols)

    start_date, end_date = (date_range if isinstance(date_range, tuple) and len(date_range) == 2
                             else (date_range, date_range))

    mask = (df[date_col].dt.date >= start_date) & (df[date_col].dt.date <= end_date)
    filtered = df.loc[mask].sort_values(by=sr_col)
    st.caption(f"Showing **{len(filtered)}** rows  |  {start_date} → {end_date}")

    col_chart, col_metrics = st.columns([3, 1])
    with col_chart:
        if not selected_cols:
            st.info("Select at least one column from the sidebar to plot.")
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

    with st.expander("📋 Raw data"):
        st.dataframe(filtered, use_container_width=True)

    st.download_button(
        "⬇️ Download CSV", filtered.to_csv(index=False).encode(),
        file_name=f"{sheet_name.replace(' ','_')}_filtered.csv", mime="text/csv",
    )


# =================================================================
# RENDER 4 — OTHER QC WORKBOOK TABS (generic raw view)
# =================================================================
def render_generic_tab(spreadsheet_id: str, sheet_name: str):
    try:
        raw_df = fetch_sheet_csv(spreadsheet_id, sheet_name, header=None)
    except Exception as e:
        st.error(f"Could not load **{sheet_name}**.\n\nDetails: {e}")
        st.stop()

    st.info(
        f"Tab **'{sheet_name}'** uses a custom layout. "
        "Showing raw data below — share the row/column structure to add a chart for this tab."
    )
    st.dataframe(raw_df, use_container_width=True)
    st.download_button(
        "⬇️ Download CSV", raw_df.to_csv(index=False).encode(),
        file_name=f"{sheet_name.replace(' ','_')}_raw.csv", mime="text/csv",
    )


# =================================================================
# ROUTING — pick the right renderer based on line type & sheet
# =================================================================
line_cfg  = LINES[line]
line_type = line_cfg["type"]
src_id    = line_cfg["id"]   # spreadsheet ID for Google Sheets, file path for Excel

if line_type == "standard":
    render_standard_sheet(src_id, sheet, line)

elif line_type == "qc_workbook":
    if sheet == "Shaft & Collar":
        render_qc_shaft_collar(src_id, sheet)
    else:
        render_generic_tab(src_id, sheet)

elif line_type == "excel_local":
    if not excel_available:
        st.error(
            "### Excel file not found\n"
            f"Expected location: `{EXCEL_FILE_PATH}`\n\n"
            "**Steps to fix:**\n"
            "1. Create a `data/` folder in your GitHub repo (same level as `app.py`).\n"
            "2. Copy your Excel file there: `data/Input Data - Crankcase Master Metal VSD Long Leg.xlsx`\n"
            "3. Commit and push to GitHub."
        )
    else:
        render_excel_sheet(src_id, sheet)
