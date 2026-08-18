"""
Velozählungen Zürich — Jahresvergleich (Streamlit)
----------------------------------------------------
Lädt automatisch die offenen Velo-/Fussgänger-Zähldaten der Stadt Zürich
für mehrere Jahre und stellt sie vergleichend dar.

Datenquelle: Open Data Zürich (Tiefbauamt)
https://data.stadt-zuerich.ch/dataset/ted_taz_verkehrszaehlungen_werte_fussgaenger_velo

HINWEIS: Testprojekt ohne Gewähr — siehe Disclaimer in der App und im README.

Lokal starten:
    pip install -r requirements.txt
    streamlit run app.py
"""

import pandas as pd
import plotly.express as px
import streamlit as st

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Velozählungen Zürich – Jahresvergleich", layout="wide")

DATASET_PAGE_URL = (
    "https://data.stadt-zuerich.ch/dataset/"
    "ted_taz_verkehrszaehlungen_werte_fussgaenger_velo"
)
CSV_URL_TEMPLATE = DATASET_PAGE_URL + "/download/{year}_verkehrszaehlungen_werte_fussgaenger_velo.csv"

AVAILABLE_YEARS = [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]

WEEKDAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WEEKDAY_LABELS_DE = {
    "Monday": "Mo", "Tuesday": "Di", "Wednesday": "Mi", "Thursday": "Do",
    "Friday": "Fr", "Saturday": "Sa", "Sunday": "So",
}


# ---------------------------------------------------------------------------
# Daten laden & aufbereiten
# ---------------------------------------------------------------------------

def find_column(columns, keywords):
    """Erste Spalte, die eines der Keywords (case-insensitive) im Namen enthält."""
    for kw in keywords:
        for c in columns:
            if kw in c.lower():
                return c
    return None


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def load_year_raw(year: int):
    """Lädt die Rohdaten eines Jahres direkt von Open Data Zürich. None falls nicht verfügbar."""
    url = CSV_URL_TEMPLATE.format(year=year)
    try:
        return pd.read_csv(url, storage_options={"User-Agent": "Mozilla/5.0 (VeloDashboard/1.0)"})
    except Exception:
        return None


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def prepare_year(df: pd.DataFrame) -> pd.DataFrame:
    """Erkennt relevante Spalten automatisch, bereinigt Typen, ergänzt Hilfsspalten."""
    cols = df.columns.tolist()
    date_col = find_column(cols, ["datum", "zeitstempel", "messung"])
    velo_in_col = find_column(cols, ["velo_in", "velo"])
    velo_out_col = find_column(cols, ["velo_out"])
    standort_col = find_column(cols, ["fk_standort", "fk_zaehler", "standort"])

    if date_col is None or velo_in_col is None:
        raise ValueError(f"Benötigte Spalten nicht gefunden. Vorhandene Spalten: {cols}")

    keep = [date_col, velo_in_col]
    if velo_out_col:
        keep.append(velo_out_col)
    if standort_col:
        keep.append(standort_col)

    out = df[keep].copy()
    rename_map = {date_col: "datum", velo_in_col: "velo_in"}
    if velo_out_col:
        rename_map[velo_out_col] = "velo_out"
    if standort_col:
        rename_map[standort_col] = "standort"
    out = out.rename(columns=rename_map)

    out = out.dropna(subset=["datum", "velo_in"])
    out["datum"] = pd.to_datetime(out["datum"], errors="coerce")
    out = out.dropna(subset=["datum"])

    if "velo_out" not in out.columns:
        out["velo_out"] = 0
    out["velo_out"] = out["velo_out"].fillna(0)
    out["velo_total"] = out["velo_in"] + out["velo_out"]

    if "standort" not in out.columns:
        out["standort"] = "ALL"
    out["standort"] = out["standort"].astype(str)

    out["wochentag"] = out["datum"].dt.day_name()
    out["uhrzeit"] = out["datum"].dt.strftime("%H:%M")
    out["tag"] = out["datum"].dt.date
    return out


def filter_location(df: pd.DataFrame, location: str) -> pd.DataFrame:
    if location == "Alle Zählstellen":
        return df
    return df[df["standort"] == location]


# ---------------------------------------------------------------------------
# Aggregationen
# ---------------------------------------------------------------------------

def weekday_quarter_avg(df: pd.DataFrame, metric_col: str) -> pd.Series:
    return df.groupby("wochentag")[metric_col].mean().reindex(WEEKDAY_ORDER)


def weekday_daily_avg(df: pd.DataFrame, metric_col: str) -> pd.Series:
    daily_sum = df.groupby("tag")[metric_col].sum()
    wd_map = df.groupby("tag")["wochentag"].first()
    combined = pd.DataFrame({"total": daily_sum, "wochentag": wd_map})
    return combined.groupby("wochentag")["total"].mean().reindex(WEEKDAY_ORDER)


def time_of_day_avg(df: pd.DataFrame, metric_col: str) -> pd.Series:
    return df.groupby("uhrzeit")[metric_col].mean().sort_index()


def year_totals(df: pd.DataFrame, metric_col: str):
    total = df[metric_col].sum()
    days = df["tag"].nunique()
    avg_per_day = total / days if days > 0 else 0
    return total, days, avg_per_day


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.title("🚲 Velozählungen Zürich — Jahresvergleich")

st.warning(
    "**Ohne Gewähr:** Dies ist ein privates Testprojekt zu Übungszwecken. "
    "Für die Richtigkeit, Vollständigkeit oder dauerhafte Funktionstüchtigkeit dieser Darstellung "
    "wird keine Verantwortung übernommen. Bei Fragen zu den Rohdaten wende dich an die "
    f"[Datenquelle: Open Data Zürich – Fuss- und Veloverkehr]({DATASET_PAGE_URL})."
)

with st.sidebar:
    st.header("Filter")
    selected_years = st.multiselect(
        "Jahre", AVAILABLE_YEARS, default=[y for y in AVAILABLE_YEARS if y in (2024, 2025)]
    )
    metric_label = st.radio("Messwert", ["Zufahrt (VELO_IN)", "Total (IN + OUT)"])
    metric_col = "velo_in" if metric_label.startswith("Zufahrt") else "velo_total"
    view = st.radio(
        "Ansicht",
        [
            "Ø pro Viertelstunde nach Wochentag",
            "Ø Tagestotal nach Wochentag",
            "Tagesverlauf (Uhrzeit)",
            "Jahrestotal",
        ],
    )

if not selected_years:
    st.info("Bitte mindestens ein Jahr in der Seitenleiste auswählen.")
    st.stop()

datasets = {}
with st.spinner("Lade Daten von Open Data Zürich ..."):
    for year in selected_years:
        raw = load_year_raw(year)
        if raw is None:
            st.sidebar.error(f"{year}: Datensatz nicht verfügbar (noch nicht publiziert oder URL geändert)")
            continue
        try:
            datasets[year] = prepare_year(raw)
        except ValueError as e:
            st.sidebar.error(f"{year}: {e}")

if not datasets:
    st.error("Keine Daten laden können. Bitte später erneut versuchen oder Datenquelle prüfen.")
    st.stop()

all_locations = sorted(set().union(*[set(df["standort"].unique()) for df in datasets.values()]))
location = st.sidebar.selectbox("Zählstelle", ["Alle Zählstellen"] + all_locations)

# ---------------------------------------------------------------------------
# Darstellung je nach gewählter Ansicht
# ---------------------------------------------------------------------------

if view == "Jahrestotal":
    cols = st.columns(len(datasets))
    rows = []
    for (year, df), col in zip(sorted(datasets.items()), cols):
        filtered = filter_location(df, location)
        total, days, avg_per_day = year_totals(filtered, metric_col)
        col.metric(f"{year}", f"{avg_per_day:,.0f} / Tag".replace(",", "'"))
        col.caption(f"Summe: {total:,.0f}".replace(",", "'") + f" · {days} erfasste Tage")
        rows.append({"Jahr": str(year), "Ø pro Tag": avg_per_day})

    chart_df = pd.DataFrame(rows)
    fig = px.bar(chart_df, x="Jahr", y="Ø pro Tag", color="Jahr", text_auto=".0f")
    fig.update_layout(showlegend=False, yaxis_title="Ø Velos pro erfasstem Tag")
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Ø pro Tag statt reiner Jahressumme, damit unvollständig erfasste Jahre "
        "(z.B. laufendes Jahr) fair vergleichbar bleiben."
    )

else:
    long_rows = []
    for year, df in sorted(datasets.items()):
        filtered = filter_location(df, location)
        if view == "Ø pro Viertelstunde nach Wochentag":
            series = weekday_quarter_avg(filtered, metric_col)
            x_label = "Wochentag"
        elif view == "Ø Tagestotal nach Wochentag":
            series = weekday_daily_avg(filtered, metric_col)
            x_label = "Wochentag"
        else:  # Tagesverlauf
            series = time_of_day_avg(filtered, metric_col)
            x_label = "Uhrzeit"

        for idx, value in series.items():
            label = WEEKDAY_LABELS_DE.get(idx, idx) if x_label == "Wochentag" else idx
            long_rows.append({x_label: label, "Wert": value, "Jahr": str(year)})

    chart_df = pd.DataFrame(long_rows)

    if view in ("Ø pro Viertelstunde nach Wochentag", "Ø Tagestotal nach Wochentag"):
        order = [WEEKDAY_LABELS_DE[d] for d in WEEKDAY_ORDER]
        fig = px.bar(
            chart_df, x="Wochentag", y="Wert", color="Jahr", barmode="group",
            category_orders={"Wochentag": order},
        )
    else:
        fig = px.line(chart_df, x="Uhrzeit", y="Wert", color="Jahr")
        fig.update_xaxes(tickangle=45, nticks=24)

    y_title = (
        "Ø Anzahl Velos pro Tag (Tagessumme)"
        if view == "Ø Tagestotal nach Wochentag"
        else "Ø Anzahl Velos (Viertelstundenwert)"
    )
    fig.update_layout(yaxis_title=y_title)
    st.plotly_chart(fig, use_container_width=True)

st.divider()
st.caption(
    f"Datenquelle: [Open Data Zürich – Fuss- und Veloverkehr]({DATASET_PAGE_URL}) · "
    "Werte automatisch bei jedem Laden neu abgerufen. "
    "Dieses Projekt steht in keiner Verbindung zur Stadt Zürich."
    "Published by Martin Mattli https://www.linkedin.com/in/martin-mattli-441432b7/."
)
