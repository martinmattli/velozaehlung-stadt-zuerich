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
import plotly.graph_objects as go
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

MIV_DATASET_PAGE_URL = "https://data.stadt-zuerich.ch/dataset/sid_dav_verkehrszaehlung_miv_od2031"
MIV_CSV_URL_TEMPLATE = MIV_DATASET_PAGE_URL + "/download/sid_dav_verkehrszaehlung_miv_OD2031_{year}.csv"
MIV_INDEX_BASE_YEAR = 2019

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
def load_year_aggregated(year: int):
    """
    Lädt die Rohdaten eines Jahres, bereinigt sie und verdichtet sie SOFORT zu drei
    kleinen Aggregattabellen (ein paar hundert bis paar tausend Zeilen statt ~800'000).

    Nur diese kompakten Tabellen werden gecacht - die riesige Rohtabelle existiert nur
    kurz innerhalb dieser Funktion und wird danach freigegeben. Das hält den Speicherbedarf
    auch bei vielen gleichzeitig ausgewählten Jahren klein (wichtig auf Streamlit Cloud,
    wo nur ca. 1 GB RAM zur Verfügung steht).

    Rückgabe: dict mit
        "loc_wd"     -> pro (Standort, Wochentag): Summe & Anzahl Viertelstundenwerte
        "loc_tod"    -> pro (Standort, Uhrzeit):    Summe & Anzahl Viertelstundenwerte
        "daily"      -> pro (Standort, Tag):        Tagessumme + Wochentag
        "locations"  -> Liste aller Standort-IDs in diesem Jahr
    None, falls das Jahr nicht verfügbar ist oder Spalten nicht erkannt wurden.
    """
    url = CSV_URL_TEMPLATE.format(year=year)
    try:
        raw = pd.read_csv(url, storage_options={"User-Agent": "Mozilla/5.0 (VeloDashboard/1.0)"})
    except Exception:
        return None

    cols = raw.columns.tolist()
    date_col = find_column(cols, ["datum", "zeitstempel", "messung"])
    velo_in_col = find_column(cols, ["velo_in", "velo"])
    velo_out_col = find_column(cols, ["velo_out"])
    standort_col = find_column(cols, ["fk_standort", "fk_zaehler", "standort"])

    if date_col is None or velo_in_col is None:
        return None

    keep = [date_col, velo_in_col]
    if velo_out_col:
        keep.append(velo_out_col)
    if standort_col:
        keep.append(standort_col)

    df = raw[keep].copy()
    del raw  # Rohdaten so früh wie möglich freigeben

    rename_map = {date_col: "datum", velo_in_col: "velo_in"}
    if velo_out_col:
        rename_map[velo_out_col] = "velo_out"
    if standort_col:
        rename_map[standort_col] = "standort"
    df = df.rename(columns=rename_map)

    df = df.dropna(subset=["datum", "velo_in"])
    df["datum"] = pd.to_datetime(df["datum"], errors="coerce")
    df = df.dropna(subset=["datum"])

    if "velo_out" not in df.columns:
        df["velo_out"] = 0
    df["velo_out"] = df["velo_out"].fillna(0)
    df["velo_total"] = df["velo_in"] + df["velo_out"]

    if "standort" not in df.columns:
        df["standort"] = "ALL"
    df["standort"] = df["standort"].astype(str)

    df["wochentag"] = df["datum"].dt.day_name()
    df["uhrzeit"] = df["datum"].dt.strftime("%H:%M")
    df["tag"] = df["datum"].dt.date

    # --- Verdichtung: nur noch die drei kleinen Ergebnistabellen behalten ---
    loc_wd = (
        df.groupby(["standort", "wochentag"])
        .agg(vi_sum=("velo_in", "sum"), vt_sum=("velo_total", "sum"), n=("velo_in", "size"))
        .reset_index()
    )
    loc_tod = (
        df.groupby(["standort", "uhrzeit"])
        .agg(vi_sum=("velo_in", "sum"), vt_sum=("velo_total", "sum"), n=("velo_in", "size"))
        .reset_index()
    )
    daily = (
        df.groupby(["standort", "tag"])
        .agg(vi_sum=("velo_in", "sum"), vt_sum=("velo_total", "sum"))
        .reset_index()
    )
    daily["wochentag"] = pd.to_datetime(daily["tag"]).dt.day_name()

    locations = sorted(df["standort"].unique())
    del df  # bereinigte Vollständige Tabelle ebenfalls freigeben

    return {"loc_wd": loc_wd, "loc_tod": loc_tod, "daily": daily, "locations": locations}


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def load_miv_daily(year: int) -> pd.DataFrame | None:
    """
    Lädt MIV-Zähldaten (Autos/Motorräder) eines Jahres und aggregiert zu Tagessummen.
    Gibt DataFrame mit Spalten [tag, miv_total] zurück, oder None bei Fehler.
    Nur Messungen mit Status "Gemessen" werden berücksichtigt.
    """
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


def _filter_loc(table: pd.DataFrame, location: str) -> pd.DataFrame:
    if location == "Alle Zählstellen":
        return table
    return table[table["standort"] == location]


# ---------------------------------------------------------------------------
# Aggregationen (arbeiten auf den bereits verdichteten Tabellen)
# ---------------------------------------------------------------------------

def weekday_quarter_avg(loc_wd: pd.DataFrame, location: str, sum_col: str) -> pd.Series:
    df = _filter_loc(loc_wd, location)
    g = df.groupby("wochentag")[[sum_col, "n"]].sum()
    avg = g[sum_col] / g["n"]
    return avg.reindex(WEEKDAY_ORDER)


def time_of_day_avg(loc_tod: pd.DataFrame, location: str, sum_col: str) -> pd.Series:
    df = _filter_loc(loc_tod, location)
    g = df.groupby("uhrzeit")[[sum_col, "n"]].sum()
    avg = g[sum_col] / g["n"]
    return avg.sort_index()


def weekday_daily_avg(daily: pd.DataFrame, location: str, sum_col: str) -> pd.Series:
    df = _filter_loc(daily, location)
    per_tag = df.groupby("tag")[sum_col].sum()
    wd_map = df.groupby("tag")["wochentag"].first()
    combined = pd.DataFrame({"total": per_tag, "wochentag": wd_map})
    return combined.groupby("wochentag")["total"].mean().reindex(WEEKDAY_ORDER)


def year_totals(daily: pd.DataFrame, location: str, sum_col: str):
    df = _filter_loc(daily, location)
    total = df[sum_col].sum()
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
    _cached_locations = st.session_state.get("available_locations", [])
    _location_options_form = ["Alle Zählstellen"] + _cached_locations
    _current_loc = st.session_state.get("location", "Alle Zählstellen")
    _loc_idx = _location_options_form.index(_current_loc) if _current_loc in _location_options_form else 0

    with st.form("filter_form"):
        selected_years_input = st.multiselect(
            "Jahre",
            AVAILABLE_YEARS,
            default=st.session_state.get("years", [y for y in AVAILABLE_YEARS if y in (2024, 2025)]),
        )
        metric_label_input = st.radio(
            "Messwert",
            ["Zufahrt (VELO_IN)", "Total (IN + OUT)"],
            index=["Zufahrt (VELO_IN)", "Total (IN + OUT)"].index(
                st.session_state.get("metric_label", "Zufahrt (VELO_IN)")
            ),
        )
        view_options = [
            "Jahrestotal",
            "Ø pro Viertelstunde nach Wochentag",
            "Ø Tagestotal nach Wochentag",
            "Tagesverlauf (Uhrzeit)",
            "Tagessummen (Datumsbereich)",
            "Velo vs. MIV (Index 2019=100)",
        ]
        view_input = st.radio(
            "Ansicht",
            view_options,
            index=view_options.index(st.session_state.get("view", "Jahrestotal")),
        )
        location_input = st.selectbox(
            "Zählstelle",
            _location_options_form,
            index=_loc_idx,
            help="Wird nach dem ersten Laden mit allen verfügbaren Zählstellen befüllt.",
        )
        submitted = st.form_submit_button("📥 Daten laden", use_container_width=True)

    if submitted:
        st.session_state["years"] = selected_years_input
        st.session_state["metric_label"] = metric_label_input
        st.session_state["view"] = view_input
        st.session_state["location"] = location_input

# Erstmaliger Aufruf (vor jedem Klick auf "Daten laden"): sinnvolle Defaults verwenden
selected_years = st.session_state.get("years", [y for y in AVAILABLE_YEARS if y in (2024, 2025)])
metric_label = st.session_state.get("metric_label", "Zufahrt (VELO_IN)")
view = st.session_state.get("view", "Jahrestotal")
metric_col = "velo_in" if metric_label.startswith("Zufahrt") else "velo_total"

if not selected_years:
    st.info("Bitte mindestens ein Jahr auswählen und auf 'Daten laden' klicken.")
    st.stop()

datasets = {}
with st.spinner("Lade Velozähldaten von Open Data Zürich …"):
    for year in selected_years:
        agg = load_year_aggregated(year)
        if agg is None:
            st.sidebar.error(f"{year}: Datensatz nicht verfügbar oder Spalten nicht erkannt")
            continue
        datasets[year] = agg

if not datasets:
    st.error("Keine Daten laden können. Bitte später erneut versuchen oder Datenquelle prüfen.")
    st.stop()

# --- Zählstellen: verfügbare Standorte in session_state aktualisieren ---
all_locations = sorted(set().union(*[set(d["locations"]) for d in datasets.values()]))
st.session_state["available_locations"] = all_locations

location_options = ["Alle Zählstellen"] + all_locations
location = st.session_state.get("location", "Alle Zählstellen")
if location not in location_options:
    location = "Alle Zählstellen"
    st.session_state["location"] = location

sum_col = "vi_sum" if metric_col == "velo_in" else "vt_sum"

# ---------------------------------------------------------------------------
# Darstellung je nach gewählter Ansicht
# ---------------------------------------------------------------------------

if view == "Jahrestotal":
    rows = []
    for year, agg in sorted(datasets.items()):
        total, days, avg_per_day = year_totals(agg["daily"], location, sum_col)
        n_total = len(agg["locations"])
        if location == "Alle Zählstellen":
            zaehler_label = str(n_total)
        else:
            zaehler_label = f"1 / {n_total}"
        rows.append(
            {
                "Jahr": year,
                "Zählstellen": zaehler_label,
                "Ø pro Tag": round(avg_per_day),
                "Summe (erfasster Zeitraum)": round(total),
                "Erfasste Tage": days,
            }
        )

    summary_df = pd.DataFrame(rows)

    # Tabelle statt Spalten-Layout, damit auch viele Jahre nicht abgeschnitten werden
    st.dataframe(
        summary_df.style.format(
            {"Ø pro Tag": "{:,.0f}", "Summe (erfasster Zeitraum)": "{:,.0f}"}
        ).format({"Jahr": "{:d}"}),
        use_container_width=True,
        hide_index=True,
    )

    chart_df = summary_df.rename(columns={"Jahr": "JahrLabel"})
    chart_df["Jahr"] = chart_df["JahrLabel"].astype(str)
    fig = px.bar(chart_df, x="Jahr", y="Ø pro Tag", color="Jahr", text_auto=".0f")
    fig.update_layout(showlegend=False, yaxis_title="Ø Velos pro erfasstem Tag")
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Ø pro Tag statt reiner Jahressumme, damit unvollständig erfasste Jahre "
        "(z.B. laufendes Jahr) fair vergleichbar bleiben."
    )

elif view == "Tagessummen (Datumsbereich)":
    MONTH_NAMES = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
                   "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
    col_slider, col_smooth = st.columns([3, 1])
    with col_slider:
        month_range = st.select_slider(
            "Monatszeitraum",
            options=MONTH_NAMES,
            value=("Jan", "Dez"),
        )
    with col_smooth:
        smooth_mode = st.radio(
            "Kurvenanpassung",
            ["Rohdaten", "Wochenverlauf", "Jahresverlauf"],
            index=1,
        )

    smooth_descriptions = {
        "Rohdaten": "Tägliche Messwerte ohne Glättung.",
        "Wochenverlauf": "7-Tage-Durchschnitt: Glättet den typischen Wochenrhythmus (Wochentage vs. Wochenende), zeigt kurzfristige Schwankungen.",
        "Jahresverlauf": "30-Tage-Durchschnitt: Zeigt den saisonalen Trend über das Jahr (Frühling, Sommer, Herbst, Winter).",
    }
    st.caption(smooth_descriptions[smooth_mode])

    start_month = MONTH_NAMES.index(month_range[0]) + 1
    end_month = MONTH_NAMES.index(month_range[1]) + 1

    year_dfs = {}
    for year, agg in sorted(datasets.items()):
        df = _filter_loc(agg["daily"], location).copy()
        df["tag"] = pd.to_datetime(df["tag"])
        # Bei "Alle Zählstellen" gibt es mehrere Zeilen pro Tag → erst summieren
        df = df.groupby("tag", as_index=False)[sum_col].sum()
        df = df.sort_values("tag")
        df = df[(df["tag"].dt.month >= start_month) & (df["tag"].dt.month <= end_month)]
        df["Datum"] = df["tag"].dt.strftime("%m-%d")
        df["rolling7"] = df[sum_col].rolling(7, center=True, min_periods=1).mean()
        df["rolling30"] = df[sum_col].rolling(30, center=True, min_periods=7).mean()
        year_dfs[str(year)] = df

    if year_dfs:
        colors = px.colors.qualitative.Plotly
        fig = go.Figure()
        for i, (year_str, df) in enumerate(year_dfs.items()):
            color = colors[i % len(colors)]
            if smooth_mode == "Rohdaten":
                fig.add_trace(go.Scatter(
                    x=df["Datum"], y=df[sum_col],
                    mode="lines", name=year_str,
                    line=dict(color=color, width=1.5),
                    legendgroup=year_str,
                ))
            else:
                smooth_col = "rolling7" if smooth_mode == "Wochenverlauf" else "rolling30"
                # Rohdaten dünn im Hintergrund
                fig.add_trace(go.Scatter(
                    x=df["Datum"], y=df[sum_col],
                    mode="lines", name=year_str,
                    line=dict(color=color, width=1),
                    opacity=0.25,
                    legendgroup=year_str,
                    showlegend=False,
                ))
                # Glättungskurve dick im Vordergrund
                fig.add_trace(go.Scatter(
                    x=df["Datum"], y=df[smooth_col],
                    mode="lines", name=year_str,
                    line=dict(color=color, width=2.5),
                    legendgroup=year_str,
                    showlegend=True,
                ))

        fig.update_xaxes(
            tickangle=45,
            tickvals=[f"{m:02d}-01" for m in range(start_month, end_month + 1)],
            ticktext=[MONTH_NAMES[m - 1] for m in range(start_month, end_month + 1)],
        )
        fig.update_layout(yaxis_title="Tagessumme Velos", legend_title="Jahr")
        st.plotly_chart(fig, use_container_width=True)

        # Zählstellen-Angabe pro Jahr
        zaehler_parts = []
        for year, agg in sorted(datasets.items()):
            n = len(agg["locations"]) if location == "Alle Zählstellen" else 1
            zaehler_parts.append(f"{year}: {n} Zählstelle{'n' if n != 1 else ''}")
        st.caption("Erfasste Zählstellen — " + " · ".join(zaehler_parts))
    else:
        st.info("Keine Daten für diesen Zeitraum.")

else:
    long_rows = []
    for year, agg in sorted(datasets.items()):
        if view == "Ø pro Viertelstunde nach Wochentag":
            series = weekday_quarter_avg(agg["loc_wd"], location, sum_col)
            x_label = "Wochentag"
        elif view == "Ø Tagestotal nach Wochentag":
            series = weekday_daily_avg(agg["daily"], location, sum_col)
            x_label = "Wochentag"
        else:  # Tagesverlauf
            series = time_of_day_avg(agg["loc_tod"], location, sum_col)
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


# ---------------------------------------------------------------------------
# Velo vs. MIV Index-Vergleich
# ---------------------------------------------------------------------------

if view == "Velo vs. MIV (Index 2019=100)":
    st.info(
        f"Beide Verkehrsträger werden auf das Basisjahr {MIV_INDEX_BASE_YEAR} = 100 normiert. "
        "So ist direkt ablesbar, ob Velos stärker gewachsen oder gesunken sind als der Autoverkehr — "
        "unabhängig von den sehr unterschiedlichen absoluten Zählwerten."
    )

    years_to_load = sorted(set(selected_years) | {MIV_INDEX_BASE_YEAR})

    with st.spinner("Lade MIV-Daten (Motorfahrzeuge) von Open Data Zürich …"):
        miv_daily = {}
        for y in years_to_load:
            df = load_miv_daily(y)
            if df is not None:
                miv_daily[y] = df
            elif y != MIV_INDEX_BASE_YEAR:
                st.warning(f"MIV-Daten {y} nicht verfügbar.")

    if MIV_INDEX_BASE_YEAR not in miv_daily:
        st.error(f"Basisjahr {MIV_INDEX_BASE_YEAR} für MIV nicht verfügbar — Index kann nicht berechnet werden.")
        st.stop()

    def monthly_avg(daily_df: pd.DataFrame, val_col: str) -> pd.Series:
        """Ø pro Tag pro Monat (Tagessumme / Anzahl Tage im Monat)."""
        d = daily_df.copy()
        d["tag"] = pd.to_datetime(d["tag"])
        d["monat"] = d["tag"].dt.month
        return d.groupby("monat")[val_col].mean()

    # Velo: stadtweite Tagessummen aus bereits geladenen datasets
    velo_daily_by_year = {}
    for y, agg in datasets.items():
        df = agg["daily"].copy()
        df["tag"] = pd.to_datetime(df["tag"])
        velo_daily_by_year[y] = df.groupby("tag", as_index=False)[sum_col].sum().rename(columns={sum_col: "velo_total"})

    # Basisjahr-Monatsmittel
    if MIV_INDEX_BASE_YEAR not in velo_daily_by_year:
        # Basisjahr Velo nachladen falls nicht in datasets
        with st.spinner(f"Lade Velo-Basisdaten {MIV_INDEX_BASE_YEAR} …"):
            base_agg = load_year_aggregated(MIV_INDEX_BASE_YEAR)
        if base_agg:
            base_df = base_agg["daily"].copy()
            base_df["tag"] = pd.to_datetime(base_df["tag"])
            velo_daily_by_year[MIV_INDEX_BASE_YEAR] = base_df.groupby("tag", as_index=False)[sum_col].sum().rename(columns={sum_col: "velo_total"})

    velo_base = monthly_avg(velo_daily_by_year[MIV_INDEX_BASE_YEAR], "velo_total")
    miv_base = monthly_avg(miv_daily[MIV_INDEX_BASE_YEAR], "miv_total")

    MONTH_NAMES_IDX = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
                       "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
    colors = px.colors.qualitative.Plotly
    fig = go.Figure()

    for i, year in enumerate(sorted(selected_years)):
        color = colors[i % len(colors)]
        year_label = str(year)

        # Velo-Index
        if year in velo_daily_by_year:
            velo_monthly = monthly_avg(velo_daily_by_year[year], "velo_total")
            velo_idx = (velo_monthly / velo_base * 100).reindex(range(1, 13))
            fig.add_trace(go.Scatter(
                x=[MONTH_NAMES_IDX[m - 1] for m in velo_idx.index],
                y=velo_idx.values,
                mode="lines+markers",
                name=f"Velo {year_label}",
                line=dict(color=color, width=2.5, dash="solid"),
                legendgroup=year_label,
            ))

        # MIV-Index
        if year in miv_daily:
            miv_monthly = monthly_avg(miv_daily[year], "miv_total")
            miv_idx = (miv_monthly / miv_base * 100).reindex(range(1, 13))
            fig.add_trace(go.Scatter(
                x=[MONTH_NAMES_IDX[m - 1] for m in miv_idx.index],
                y=miv_idx.values,
                mode="lines+markers",
                name=f"MIV {year_label}",
                line=dict(color=color, width=2.5, dash="dot"),
                legendgroup=year_label,
            ))

    fig.add_hline(y=100, line_dash="dash", line_color="gray", line_width=1,
                  annotation_text=f"Basis {MIV_INDEX_BASE_YEAR}", annotation_position="top left")
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
    f"Datenquelle: [Open Data Zürich – Fuss- und Veloverkehr]({DATASET_PAGE_URL}) · "
    "Werte automatisch bei jedem Laden neu abgerufen. "
    "Dieses Projekt steht in keiner Verbindung zur Stadt Zürich."
    "Published by Martin Mattli https://www.linkedin.com/in/martin-mattli-441432b7/." )