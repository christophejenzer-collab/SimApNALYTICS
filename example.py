"""Beispiel-Workflow: einloggen -> abrufen -> cachen -> analysieren.

Vorbereitung (einmalig):
  1. API-Client beantragen: kissimap.ch/de/anleitungen -> "Antrag auf API Client"
  2. Nach Freigabe Umgebungsvariablen setzen:
       export SIMAP_ENV=int                # erst Testumgebung
       export SIMAP_CLIENT_ID=<deine_client_id>
       export SIMAP_REDIRECT_URI=http://localhost:8765/callback
       # optional confidential client:
       export SIMAP_CLIENT_SECRET=<secret>
       # optional langlebiger Refresh:
       export SIMAP_SCOPE="openid profile offline_access"
  3. Endpunkt-Pfade in config.py gegen die Swagger-Doku verifizieren.

Beim ersten Lauf oeffnet sich der Browser fuer Login + 2FA. Danach haelt
sich das Tool ueber den Refresh Token selbst am Leben (Token-Cache).
"""
from simapnalytics.api.client import SimapClient
from simapnalytics.models import Publication
from simapnalytics.storage.store import Store
from simapnalytics.analysis import analyzer as az


def main() -> None:
    client = SimapClient()      # holt Token automatisch (Login/Refresh/Cache)
    store = Store()

    # 1) Daten holen (Beispiel: Bau-CPV 45*, Zeitraum 2025)
    raw = client.search_publications(
        cpv=["45"], date_from="2025-01-01", date_to="2025-12-31"
    )
    pubs = [Publication.from_raw(r) for r in raw]
    print(f"{len(pubs)} Publikationen geladen")
    store.upsert(pubs)

    # 2) Analysieren
    df = az.to_frame(store.load())

    print("\n== Top-Gewinner ==")
    print(az.market_winners(df, top=10).to_string(index=False))

    print("\n== Wettbewerbsdichte je Kanton ==")
    print(az.competition_density(df).to_string(index=False))

    print("\n== Offene Leads (CPV 4520*, Kanton BE) ==")
    leads = az.find_leads(df, cpv_prefixes=["4520"], cantons=["BE"])
    print(leads[["date", "title", "proc_office"]].head(10).to_string(index=False))

    print("\n== Volumen pro Monat ==")
    print(az.volume_over_time(df).to_string(index=False))

    store.close()


if __name__ == "__main__":
    main()
