"""
Velozählungen Zürich — Seite 1: Velo-Analyse
---------------------------------------------
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

from utils import (
    AVAILABLE_YEARS,
    DATASET_PAGE_URL,
    WEEKDAY_LABELS_DE,
    WEEKDAY_ORDER,
    _filter_loc,
    load_year_aggregated,
    time_of_day_avg,
    weekday_daily_avg,
    weekday_quarter_avg,
    year_totals,
)

# ---------------------------------------------------------------------------
# Seitenkonfiguration
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Velozählungen Zürich", layout="wide")

st.title("🚲 Velozählungen Zürich — Jahresvergleich")

st.warning(
    "**Ohne Gewähr:** Dies ist ein privates Testprojekt zu Übungszwecken. "
    "Für die Richtigkeit, Vollständigkeit oder dauerhafte Funktionstüchtigkeit dieser Darstellung "
    "wird keine Verantwortung übernommen. Bei Fragen zu den Rohdaten wende dich an die "
    f"[Datenquelle: Open Data Zürich – Fuss- und Veloverkehr]({DATASET_PAGE_URL})."
)

# ---------------------------------------------------------------------------
# Sidebar / Filter
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Daten laden
# ---------------------------------------------------------------------------

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

# Zählstellen in session_state aktualisieren
all_locations = sorted(set().union(*[set(d["locations"]) for d in datasets.values()]))
st.session_state["available_locations"] = all_locations

location_options = ["Alle Zählstellen"] + all_locations
location = st.session_state.get("location", "Alle Zählstellen")
if location not in location_options:
    location = "Alle Zählstellen"
    st.session_state["location"] = location

sum_col = "vi_sum" if metric_col == "velo_in" else "vt_sum"

# ---------------------------------------------------------------------------
# Darstellung
# ---------------------------------------------------------------------------

if view == "Jahrestotal":
    rows = []
    for year, agg in sorted(datasets.items()):
        total, days, avg_per_day = year_totals(agg["daily"], location, sum_col)
        n_total = len(agg["locations"])
        zaehler_label = str(n_total) if location == "Alle Zählstellen" else f"1 / {n_total}"
        rows.append({
            "Jahr": year,
            "Zählstellen": zaehler_label,
            "Ø pro Tag": round(avg_per_day),
            "Summe (erfasster Zeitraum)": round(total),
            "Erfasste Tage": days,
        })

    summary_df = pd.DataFrame(rows)
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
                fig.add_trace(go.Scatter(
                    x=df["Datum"], y=df[sum_col],
                    mode="lines", name=year_str,
                    line=dict(color=color, width=1),
                    opacity=0.25,
                    legendgroup=year_str,
                    showlegend=False,
                ))
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

st.divider()
st.caption(
    f"Datenquelle: [Open Data Zürich – Fuss- und Veloverkehr]({DATASET_PAGE_URL}) · "
    "Werte automatisch bei jedem Laden neu abgerufen. "
    "Dieses Projekt steht in keiner Verbindung zur Stadt Zürich. "
    "Published by Martin Mattli https://www.linkedin.com/in/martin-mattli-441432b7/."
)
