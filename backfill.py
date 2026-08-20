"""
Backfill-Script: Lädt Velo- und MIV-Daten 2019–2025 von Open Data Zürich
und speichert die aggregierten Tagesdaten in Supabase.

Einmalig lokal ausführen:
    pip install supabase pandas
    python backfill.py

Credentials via Umgebungsvariablen:
    export SUPABASE_URL="https://xxx.supabase.co"
    export SUPABASE_KEY="eyJ..."
"""

import os
import sys

import pandas as pd
from supabase import create_client

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

VELO_CSV_TEMPLATE = (
    "https://data.stadt-zuerich.ch/dataset/"
    "ted_taz_verkehrszaehlungen_werte_fussgaenger_velo"
    "/download/{year}_verkehrszaehlungen_werte_fussgaenger_velo.csv"
)
MIV_CSV_TEMPLATE = (
    "https://data.stadt-zuerich.ch/dataset/sid_dav_verkehrszaehlung_miv_od2031"
    "/download/sid_dav_verkehrszaehlung_miv_OD2031_{year}.csv"
)

YEARS = list(range(2019, 2026))  # 2019–2025
CHUNK_SIZE = 5_000  # Zeilen pro Supabase-Insert


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def find_column(columns, keywords):
    for kw in keywords:
        for c in columns:
            if kw in c.lower():
                return c
    return None


def upsert_chunks(client, table: str, rows: list[dict]):
    """Schreibt rows in Chunks in Supabase (upsert = update or insert)."""
    for i in range(0, len(rows), CHUNK_SIZE):
        client.table(table).upsert(rows[i:i + CHUNK_SIZE]).execute()
    print(f"  ✓ {table}: {len(rows)} Zeilen geschrieben")


# ---------------------------------------------------------------------------
# Velo laden & schreiben
# ---------------------------------------------------------------------------

def backfill_velo(client, year: int):
    print(f"\n[Velo {year}] Lade CSV …")
    url = VELO_CSV_TEMPLATE.format(year=year)
    try:
        raw = pd.read_csv(url, storage_options={"User-Agent": "Mozilla/5.0 (VeloDashboard/1.0)"})
    except Exception as e:
        print(f"  ✗ Fehler: {e}")
        return

    cols = raw.columns.tolist()
    date_col    = find_column(cols, ["datum", "zeitstempel", "messung"])
    velo_in_col = find_column(cols, ["velo_in", "velo"])
    velo_out_col = find_column(cols, ["velo_out"])
    standort_col = find_column(cols, ["fk_standort", "fk_zaehler", "standort"])

    if date_col is None or velo_in_col is None:
        print("  ✗ Spalten nicht erkannt")
        return

    keep = [date_col, velo_in_col]
    if velo_out_col:
        keep.append(velo_out_col)
    if standort_col:
        keep.append(standort_col)

    df = raw[keep].copy()
    del raw

    rename = {date_col: "datum", velo_in_col: "velo_in"}
    if velo_out_col:
        rename[velo_out_col] = "velo_out"
    if standort_col:
        rename[standort_col] = "standort"
    df = df.rename(columns=rename)

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
    df["uhrzeit"]   = df["datum"].dt.strftime("%H:%M")
    df["tag"]       = df["datum"].dt.date

    # --- velo_daily ---
    daily = (
        df.groupby(["standort", "tag"])
        .agg(vi_sum=("velo_in", "sum"), vt_sum=("velo_total", "sum"))
        .reset_index()
    )
    rows = [
        {"year": year, "standort": r.standort, "tag": str(r.tag),
         "vi_sum": float(r.vi_sum), "vt_sum": float(r.vt_sum)}
        for r in daily.itertuples()
    ]
    upsert_chunks(client, "velo_daily", rows)

    # --- velo_loc_wd ---
    loc_wd = (
        df.groupby(["standort", "wochentag"])
        .agg(vi_sum=("velo_in", "sum"), vt_sum=("velo_total", "sum"), n=("velo_in", "size"))
        .reset_index()
    )
    rows = [
        {"year": year, "standort": r.standort, "wochentag": r.wochentag,
         "vi_sum": float(r.vi_sum), "vt_sum": float(r.vt_sum), "n": int(r.n)}
        for r in loc_wd.itertuples()
    ]
    upsert_chunks(client, "velo_loc_wd", rows)

    # --- velo_loc_tod ---
    loc_tod = (
        df.groupby(["standort", "uhrzeit"])
        .agg(vi_sum=("velo_in", "sum"), vt_sum=("velo_total", "sum"), n=("velo_in", "size"))
        .reset_index()
    )
    rows = [
        {"year": year, "standort": r.standort, "uhrzeit": r.uhrzeit,
         "vi_sum": float(r.vi_sum), "vt_sum": float(r.vt_sum), "n": int(r.n)}
        for r in loc_tod.itertuples()
    ]
    upsert_chunks(client, "velo_loc_tod", rows)


# ---------------------------------------------------------------------------
# MIV laden & schreiben
# ---------------------------------------------------------------------------

def backfill_miv(client, year: int):
    print(f"\n[MIV {year}] Lade CSV …")
    url = MIV_CSV_TEMPLATE.format(year=year)
    try:
        chunks = pd.read_csv(
            url,
            usecols=["MessungDatZeit", "AnzFahrzeuge", "AnzFahrzeugeStatus", "ZSID"],
            dtype={"AnzFahrzeuge": "float32", "AnzFahrzeugeStatus": "category", "ZSID": "category"},
            encoding="utf-8-sig",
            storage_options={"User-Agent": "Mozilla/5.0 (VeloDashboard/1.0)"},
            chunksize=100_000,
        )
    except Exception as e:
        print(f"  ✗ Fehler: {e}")
        return

    daily_parts = []
    zsid_sets = []
    for chunk in chunks:
        chunk = chunk[chunk["AnzFahrzeugeStatus"] == "Gemessen"]
        chunk["tag"] = pd.to_datetime(chunk["MessungDatZeit"], errors="coerce").dt.date
        chunk = chunk.dropna(subset=["tag"])
        zsid_sets.append(set(chunk["ZSID"].unique()))
        daily_parts.append(chunk.groupby("tag", as_index=False)["AnzFahrzeuge"].sum())

    if not daily_parts:
        print("  ✗ Keine Daten")
        return

    daily = pd.concat(daily_parts).groupby("tag", as_index=False)["AnzFahrzeuge"].sum()
    n_stations = len(set().union(*zsid_sets))

    rows = [
        {"year": year, "tag": str(r.tag), "miv_total": float(r.AnzFahrzeuge), "n_stations": n_stations}
        for r in daily.itertuples()
    ]
    upsert_chunks(client, "miv_daily", rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Fehler: SUPABASE_URL und SUPABASE_KEY als Umgebungsvariablen setzen.")
        sys.exit(1)

    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print(f"Verbunden mit Supabase: {SUPABASE_URL}")

    for year in YEARS:
        backfill_velo(client, year)
        backfill_miv(client, year)

    print("\n✅ Backfill abgeschlossen.")
