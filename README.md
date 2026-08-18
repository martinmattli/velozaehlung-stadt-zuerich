# Velozählungen Zürich — Jahresvergleich

Ein kleines Streamlit-Dashboard, das die offenen Velo-/Fussgänger-Zähldaten der
Stadt Zürich automatisch lädt und über mehrere Jahre vergleichend darstellt
(Wochentagsmuster, Tagesverlauf, Jahrestotale).

## ⚠️ Disclaimer

Dies ist ein **privates Testprojekt zu Übungszwecken**, entstanden im Rahmen einer
persönlichen Auseinandersetzung mit Open-Data-Werkzeugen. Es besteht **keine
Verbindung zur Stadt Zürich** oder zum Tiefbauamt.

- **Ohne Gewähr:** Es wird keine Verantwortung für die Richtigkeit, Vollständigkeit
  oder dauerhafte Funktionstüchtigkeit dieser App oder ihrer Darstellungen übernommen.
- Die App verändert die Rohdaten nicht inhaltlich, sondern aggregiert sie nur
  (Mittelwerte, Summen). Für verbindliche Auswertungen bitte immer die Originaldaten
  konsultieren.
- Dieses Projekt wird nicht aktiv gewartet und kann jederzeit fehlerhaft sein oder
  nicht mehr funktionieren (z.B. wenn sich die Struktur der Quelldaten ändert).

## Datenquelle

Alle Daten stammen von **Open Data Zürich** (Tiefbauamt, Stadt Zürich):

📊 [Daten der automatischen Fussgänger- und Velozählung](https://data.stadt-zuerich.ch/dataset/ted_taz_verkehrszaehlungen_werte_fussgaenger_velo)

Die App lädt die CSV-Dateien der gewählten Jahre direkt von dieser Quelle und
zwischenspeichert sie für 24 Stunden.

## Lokal starten

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Features

- Automatischer Download der Jahresdaten (kein manueller CSV-Upload nötig)
- Filter nach Zählstelle, Messwert (Zufahrt vs. Total) und Ansicht
- Vier Ansichten: Ø pro Viertelstunde nach Wochentag, Ø Tagestotal nach Wochentag,
  Tagesverlauf, Jahrestotal (mit fairer Ø-pro-Tag-Normalisierung für unvollständige Jahre)

## Lizenz / Weiterverwendung

Der Code hier darf frei verwendet und angepasst werden. Für die Nutzungsbedingungen
der zugrunde liegenden Daten gelten die Bedingungen von Open Data Zürich
(siehe Datenquellen-Link oben).
