"""Zuschlaege zu Ausschreibungen finden und auswerten.

Beantwortet genau: Wer hat den Zuschlag bekommen, wann (Zuschlagsdatum),
fuer wie viel, und ueber welchen Zeitraum laeuft die Beschaffung.

KEIN Login noetig - nutzt die oeffentliche simap-API.

Beispiel:
  python find_awards.py --suche "Strassenbau" --kanton BE --von 2025-01-01
"""
from __future__ import annotations

import argparse

from simapnalytics.api.client import SimapClient, AWARD_PUB_TYPES
from simapnalytics.models import Award


def main() -> None:
    p = argparse.ArgumentParser(description="simap Zuschlags-Analyse (anonym)")
    p.add_argument("--suche", help="Suchtext (min. 3 Zeichen)")
    p.add_argument("--kanton", action="append", help="Kantonscode, z.B. BE (mehrfach moeglich)")
    p.add_argument("--cpv", action="append", help="CPV-Code 8-stellig (mehrfach moeglich)")
    p.add_argument("--von", dest="von", help="Publikation ab YYYY-MM-DD")
    p.add_argument("--bis", dest="bis", help="Publikation bis YYYY-MM-DD")
    p.add_argument("--typ", action="append",
                   choices=["construction", "service", "supply"],
                   help="Projekttyp (mehrfach moeglich)")
    p.add_argument("--max", type=int, default=200, help="Max. Treffer")
    args = p.parse_args()

    client = SimapClient()  # anonym

    # Nur Zuschlags-Publikationen abfragen -> liefert award_companies etc.
    projects = client.search_projects(
        search=args.suche,
        cantons=args.kanton,
        cpv_codes=args.cpv,
        publication_from=args.von,
        publication_until=args.bis,
        project_sub_types=args.typ,
        pub_types=AWARD_PUB_TYPES,
        lang="de",
    )

    n = 0
    for raw in projects:
        a = Award.from_raw(raw)
        if not a.award_companies:
            continue
        n += 1
        print(f"\n[{n}] {a.title or '(kein Titel)'}")
        print(f"     Kanton:        {a.canton or '-'}   Stelle: {a.proc_office or '-'}")
        print(f"     Zuschlag an:   {', '.join(a.award_companies)}")
        print(f"     Zuschlagsdatum:{a.award_date or '-'}")
        if a.award_price:
            print(f"     Summe:         CHF {a.award_price:,.2f}")
        print(f"     Anbieter:      {a.nr_of_offers if a.nr_of_offers is not None else '-'}")
        zeitraum = " bis ".join(x for x in [a.project_start, a.project_end] if x) or "-"
        print(f"     Beschaffung:   {zeitraum}")
        print(f"     Verfahren:     {a.procedure or '-'}   WTO: {a.is_wto}")
        if n >= args.max:
            break

    if n == 0:
        print("Keine Zuschlaege zu diesen Kriterien gefunden.")
    else:
        print(f"\n{n} Zuschlaege gefunden.")


if __name__ == "__main__":
    main()
