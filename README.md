# SimApNALYTICS

Ausschreibungs- und Zuschlagsanalyse über die **öffentliche** simap.ch-API.
Kein Login, kein API-Antrag, gebührenfrei (nur öffentlich publizierte Daten).

## Installation
```bash
pip install -r requirements.txt
```

## Dashboard starten
```bash
streamlit run dashboard.py
```
Filter links einstellen (Suchtext, Kanton, CPV, Datum, Projekttyp), **Suchen**.
Resultate als Tabelle, Ranking der Gewinner, Trends. Export als CSV/Excel.

## CLI (ohne Dashboard)
```bash
python find_awards.py --suche "Strassenbau" --kanton BE --von 2025-01-01
python find_awards.py --cpv 45233140 --typ construction
```

## Was du bekommst (pro Zuschlag)
- Zuschlagsempfänger (`award_companies`)
- Zuschlagsdatum (`award_date`)
- Summe, Anbieterzahl, Verfahren
- Beschaffungszeitraum (`date_project_start` → `date_project_end`), sofern simap diese füllt

## Struktur
```
simapnalytics/
  config.py            # API-Basis + Endpunkt-Pfade
  auth.py              # OAuth2/OIDC (nur für geschützte Aktionen, standardmäßig AUS)
  api/client.py        # anonymer API-Client, Suche + Paginierung
  models.py            # Award / Publication (Feld-Normalisierung)
  analysis/analyzer.py # Ranking, Wettbewerb, Trends, CPV, Filter
  storage/store.py     # optionaler SQLite-Cache
dashboard.py           # Streamlit-Oberfläche
find_awards.py         # CLI
```

## Hinweise
- Endpunkte/Parameter verifiziert via simap.ch/api-doc und dem MIT-Projekt
  Digilac/simap-mcp.
- `date_project_start/end` sind bei simap oft leer – dann zeigt das Tool "-".
- Beim ersten Live-Lauf ggf. Feldnamen der v2-Suche prüfen und in models.py
  nachziehen, falls etwas abweicht.
