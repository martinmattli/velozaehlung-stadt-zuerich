"""
Velozählungen Zürich — Seite 2: Velo vs. MIV Vergleich
--------------------------------------------------------
Datenquellen:
  Velo: Open Data Zürich – Fuss- und Veloverkehr (Tiefbauamt)
  MIV:  Open Data Zürich – MIV Verkehrszählung (ASIT/DAV)
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

DATASET_PAGE_URL = (
    "https://data.stadt-zuerich.ch/dataset/"
    "ted_taz_verkehrszaehlungen_werte_fussgaenger_velo"
)
CSV_URL_TEMPLATE = DATASET_PAGE_URL + "/download/{year}_verkehrszaehlungen_werte_fussgaenger_velo.csv"

MIV_DATASET_PAGE_URL = "https://data.stadt-zuerich.ch/dataset/sid_dav_verkehrszaehlung_miv_od2031"
MIV_CSV_URL_TEMPLATE = MIV_DATASET_PAGE_URL + "/download/sid_dav_verkehrszaehlung_miv_OD2031_{year}.csv"
MIV_INDEX_BASE_YEAR = 2019

AVAILABLE_YEARS = [2019, 2020, 2021, 2022, 2023, 2024, 2025]


# ---------------------------------------------------------------------------
# Daten laden
# ---------------------------------------------------------------------------

def find_column(columns, keywords):
    for kw in keywords:
        for c in columns:
            if kw in c.lower():
                return c
    return None


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def load_velo_daily(year: int) -> pd.DataFrame | None:
    url = CSV_URL_TEMPLATE.format(year=year)
    try:
        raw = pd.read_csv(url, storage_options={"User-Agent": "Mozilla/5.0 (VeloDashboard/1.0)"})
    except Exception:
        return None

    cols = raw.columns.tolist()
    date_col = find_column(cols, ["datum", "zeitstempel", "messung"])
    velo_in_col = find_column(cols, ["velo_in", "velo"])
    if date_col is None or velo_in_col is None:
        return None

    df = raw[[date_col, velo_in_col]].copy()
    del raw
    df = df.rename(columns={date_col: "datum", velo_in_col: "velo_in"})
    df = df.dropna(subset=["datum", "velo_in"])
    df["datum"] = pd.to_datetime(df["datum"], errors="coerce")
    df = df.dropna(subset=["datum"])
    df["tag"] = df["datum"].dt.date
    daily = df.groupby("tag", as_index=False)["velo_in"].sum().rename(columns={"velo_in": "velo_total"})
    del df
    return daily


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def load_miv_daily(year: int) -> pd.DataFrame | None:
    url = MIV_CSV_URL_TEMPLATE.format(year=year)
    try:
        raw = pd.read_csv(
            url,
            usecols=["MessungDatZeit", "AnzFahrzeuge", "AnzFahrzeugeStatus"],
            encoding="utf-8-sig",
            storage_options={"User-Agent": "Mozilla/5.0 (VeloDashboard/1.0)"},
        )
    except Exception:
        return None

    raw = raw[raw["AnzFahrzeugeStatus"] == "Gemessen"].copy()
    raw["tag"] = pd.to_datetime(raw["MessungDatZeit"], errors="coerce").dt.date
    raw = raw.dropna(subset=["tag"])
    daily = raw.groupby("tag", as_index=False)["AnzFahrzeuge"].sum()
    daily = daily.rename(columns={"AnzFahrzeuge": "miv_total"})
    del raw
    return daily


def monthly_avg(daily_df: pd.DataFrame, val_col: str) -> pd.Series:
    d = daily_df.copy()
    d["tag"] = pd.to_datetime(d["tag"])
    d["monat"] = d["tag"].dt.month
    return d.groupby("monat")[val_col].mean()


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.title("🚗🚲 Velo vs. MIV — Verkehrsentwicklung Zürich")

st.info(
    f"Beide Verkehrsträger werden auf das Basisjahr **{MIV_INDEX_BASE_YEAR} = 100** normiert. "
    "So ist direkt ablesbar, ob Velos stärker gewachsen oder gesunken sind als der Autoverkehr — "
    "unabhängig von den sehr unterschiedlichen absoluten Zählwerten."
)

with st.sidebar:
    st.header("Filter")
    with st.form("filter_form"):
        selected_years_input = st.multiselect(
            "Jahre",
            AVAILABLE_YEARS,
            default=st.session_state.get("miv_years", [y for y in AVAILABLE_YEARS if y in (2019, 2022, 2024, 2025)]),
        )
        submitted = st.form_submit_button("📥 Daten laden", use_container_width=True)

    if submitted:
        st.session_state["miv_years"] = selected_years_input

    st.caption(f"Basisjahr {MIV_INDEX_BASE_YEAR} wird automatisch mitgeladen.")

selected_years = st.session_state.get("miv_years", [y for y in AVAILABLE_YEARS if y in (2019, 2022, 2024, 2025)])

if not selected_years:
    st.info("Bitte mindestens ein Jahr auswählen und auf 'Daten laden' klicken.")
    st.stop()

years_to_load = sorted(set(selected_years) | {MIV_INDEX_BASE_YEAR})

velo_by_year = {}
with st.spinner("Lade Velodaten …"):
    for y in years_to_load:
        df = load_velo_daily(y)
        if df is not None:
            velo_by_year[y] = df

miv_by_year = {}
with st.spinner("Lade MIV-Daten (Motorfahrzeuge) …"):
    for y in years_to_load:
        df = load_miv_daily(y)
        if df is not None:
            miv_by_year[y] = df
        elif y != MIV_INDEX_BASE_YEAR:
            st.warning(f"MIV-Daten {y} nicht verfügbar.")

if MIV_INDEX_BASE_YEAR not in miv_by_year or MIV_INDEX_BASE_YEAR not in velo_by_year:
    st.error(f"Basisjahr {MIV_INDEX_BASE_YEAR} konnte nicht geladen werden.")
    st.stop()

# ---------------------------------------------------------------------------
# Index berechnen & darstellen
# ---------------------------------------------------------------------------

MONTH_NAMES = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
               "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]

velo_base = monthly_avg(velo_by_year[MIV_INDEX_BASE_YEAR], "velo_total")
miv_base = monthly_avg(miv_by_year[MIV_INDEX_BASE_YEAR], "miv_total")

colors = px.colors.qualitative.Plotly
fig = go.Figure()

for i, year in enumerate(sorted(selected_years)):
    color = colors[i % len(colors)]
    year_label = str(year)

    if year in velo_by_year:
        velo_monthly = monthly_avg(velo_by_year[year], "velo_total")
        velo_idx = (velo_monthly / velo_base * 100).reindex(range(1, 13))
        fig.add_trace(go.Scatter(
            x=[MONTH_NAMES[m - 1] for m in velo_idx.index],
            y=velo_idx.values,
            mode="lines+markers",
            name=f"Velo {year_label}",
            line=dict(color=color, width=2.5, dash="solid"),
            legendgroup=year_label,
        ))

    if year in miv_by_year:
        miv_monthly = monthly_avg(miv_by_year[year], "miv_total")
        miv_idx = (miv_monthly / miv_base * 100).reindex(range(1, 13))
        fig.add_trace(go.Scatter(
            x=[MONTH_NAMES[m - 1] for m in miv_idx.index],
            y=miv_idx.values,
            mode="lines+markers",
            name=f"MIV {year_label}",
            line=dict(color=color, width=2.5, dash="dot"),
            legendgroup=year_label,
        ))

fig.add_hline(
    y=100, line_dash="dash", line_color="gray", line_width=1,
    annotation_text=f"Basis {MIV_INDEX_BASE_YEAR}",
    annotation_position="top left",
)
fig.update_layout(
    yaxis_title=f"Index ({MIV_INDEX_BASE_YEAR} = 100)",
    legend_title="Verkehrsträger · Jahr",
    hovermode="x unified",
)
st.plotly_chart(fig, use_container_width=True)

st.caption(
    f"Velo: durchgezogene Linie · MIV (Motorfahrzeuge): gepunktete Linie · "
    f"Basisjahr {MIV_INDEX_BASE_YEAR} = 100. "
    f"Velo-Datenquelle: [Open Data Zürich – Fuss-/Veloverkehr]({DATASET_PAGE_URL}). "
    f"MIV-Datenquelle: [Open Data Zürich – MIV Verkehrszählung]({MIV_DATASET_PAGE_URL})."
)

st.divider()
st.caption(
    "Dieses Projekt steht in keiner Verbindung zur Stadt Zürich. "
    "Published by Martin Mattli https://www.linkedin.com/in/martin-mattli-441432b7/."
)
