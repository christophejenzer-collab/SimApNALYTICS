"""Zuschlaege zu Ausschreibungen finden und auswerten (SimApNALYTICS).

Beantwortet: Wer hat den Zuschlag bekommen, wann (Zuschlagsdatum), fuer wie viel,
wie viele Anbieter, ueber welchen Zeitraum.  KEIN Login noetig.

Beispiel:
  python find_awards.py --suche "Sanierung" --kanton BE --von 2026-01-01
"""
from __future__ import annotations

import argparse

from simapnalytics.api.client import SimapClient


def main() -> None:
    p = argparse.ArgumentParser(description="SimApNALYTICS - simap Zuschlags-Analyse (anonym)")
    p.add_argument("--suche", help="Suchtext (min. 3 Zeichen)")
    p.add_argument("--kanton", action="append", help="Kantonscode, z.B. BE (mehrfach moeglich)")
    p.add_argument("--cpv", action="append", help="CPV-Code 8-stellig (mehrfach moeglich)")
    p.add_argument("--von", dest="von", help="Publikation ab YYYY-MM-DD")
    p.add_argument("--bis", dest="bis", help="Publikation bis YYYY-MM-DD")
    p.add_argument("--typ", action="append",
                   choices=["construction", "service", "supply"],
                   help="Projekttyp (mehrfach moeglich)")
    p.add_argument("--max", type=int, default=100, help="Max. Treffer")
    args = p.parse_args()

    client = SimapClient()  # anonym
    print("Suche laeuft (Details werden pro Zuschlag nachgeladen)…\n")

    n = 0
    for a in client.find_awards(
        search=args.suche,
        cantons=args.kanton,
        cpv_codes=args.cpv,
        publication_from=args.von,
        publication_until=args.bis,
        project_sub_types=args.typ,
        lang="de",
        max_results=args.max,
    ):
        n += 1
        print(f"[{n}] {a.title or '(kein Titel)'}")
        print(f"     Kanton:        {a.canton or '-'}   Stelle: {a.proc_office or '-'}")
        print(f"     Zuschlag an:   {', '.join(a.award_companies)}")
        print(f"     Zuschlagsdatum:{a.award_date or '-'}")
        if a.award_price is not None:
            print(f"     Summe:         {a.award_currency or 'CHF'} {a.award_price:,.2f}")
        print(f"     Anbieter:      {a.nr_of_offers if a.nr_of_offers is not None else '-'}")
        zeitraum = " bis ".join(x for x in [a.project_start, a.project_end] if x) or "-"
        print(f"     Beschaffung:   {zeitraum}")
        print(f"     Verfahren:     {a.process_type or '-'}   CPV: {', '.join(a.cpv) or '-'}")
        print()

    if n == 0:
        print("Keine Zuschlaege zu diesen Kriterien gefunden.")
    else:
        print(f"{n} Zuschlaege gefunden.")


if __name__ == "__main__":
    main()
