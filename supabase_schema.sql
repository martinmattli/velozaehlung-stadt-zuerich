-- Velozählungen Zürich — Supabase Schema
-- Einmalig im Supabase SQL Editor ausführen.

CREATE TABLE IF NOT EXISTS velo_daily (
    year        smallint NOT NULL,
    standort    text     NOT NULL,
    tag         date     NOT NULL,
    vi_sum      real     NOT NULL,
    vt_sum      real     NOT NULL,
    PRIMARY KEY (year, standort, tag)
);

CREATE TABLE IF NOT EXISTS velo_loc_wd (
    year        smallint NOT NULL,
    standort    text     NOT NULL,
    wochentag   text     NOT NULL,
    vi_sum      real     NOT NULL,
    vt_sum      real     NOT NULL,
    n           integer  NOT NULL,
    PRIMARY KEY (year, standort, wochentag)
);

CREATE TABLE IF NOT EXISTS velo_loc_tod (
    year        smallint NOT NULL,
    standort    text     NOT NULL,
    uhrzeit     text     NOT NULL,
    vi_sum      real     NOT NULL,
    vt_sum      real     NOT NULL,
    n           integer  NOT NULL,
    PRIMARY KEY (year, standort, uhrzeit)
);

CREATE TABLE IF NOT EXISTS miv_daily (
    year        smallint NOT NULL,
    tag         date     NOT NULL,
    miv_total   real     NOT NULL,
    n_stations  smallint NOT NULL,
    PRIMARY KEY (year, tag)
);

-- Indizes für schnelle Jahr-Abfragen
CREATE INDEX IF NOT EXISTS idx_velo_daily_year      ON velo_daily (year);
CREATE INDEX IF NOT EXISTS idx_velo_loc_wd_year     ON velo_loc_wd (year);
CREATE INDEX IF NOT EXISTS idx_velo_loc_tod_year    ON velo_loc_tod (year);
CREATE INDEX IF NOT EXISTS idx_miv_daily_year       ON miv_daily (year);
