"""Zuschlaege nach Anbieter analysieren (SimApNALYTICS).

Beispiel-Use-Case: Wer hat im Bereich Drucken/Kopieren Zuschlaege erhalten,
und wie schneiden Ricoh vs. Canon ab.

Strategie: serverseitig per CPV vorfiltern -> Details laden -> nach Firmenname
filtern. KEIN Login noetig (oeffentliche simap-API).

Beispiele:
  # Vergleich Ricoh vs Canon, Druck/Kopier-CPVs, seit simap-Start:
  python company_awards.py --vergleich --von 2024-07-01

  # Einzelne Firma frei abfragen:
  python company_awards.py --firma "ricoh" --von 2024-07-01
  python company_awards.py --firma "canon" --cpv 30120000 --cpv 30232100
"""
from __future__ import annotations

import argparse
from datetime import date

from simapnalytics.api.client import SimapClient

# CPV-Codes rund um Drucken / Kopieren / Printer
PRINT_CPV = [
    "30120000",  # Fotokopier- und Offsetdruckgeraete
    "30121100",  # Fotokopierer
    "30232100",  # Drucker und Plotter
    "30232110",  # Laserdrucker
    "30232130",  # Farbgrafikdrucker
    "30232150",  # Tintenstrahldrucker
    "79800000",  # Druckereidienste
    "50313000",  # Wartung/Reparatur Kopiergeraete
]


def summarize(client: SimapClient, term: str, cpv, von, bis):
    awards = list(client.find_awards_by_company(
        [term], cpv_codes=cpv, publication_from=von, publication_until=bis, lang="de"))
    total = sum(a.award_price for a in awards if a.award_price)
    return awards, total


def print_awards(label: str, awards, total: float) -> None:
    print(f"\n===== {label}: {len(awards)} Zuschlag/Zuschlaege, "
          f"Total CHF {total:,.2f} =====")
    for i, a in enumerate(awards, 1):
        preis = f"CHF {a.award_price:,.2f}" if a.award_price is not None else "-"
        print(f"[{i}] {a.award_date or '-'} | {preis} | {a.title or '(kein Titel)'}")
        print(f"     Empfaenger: {', '.join(a.award_companies)}")
        print(f"     Stelle: {a.proc_office or '-'} ({a.canton or '-'})  CPV: {', '.join(a.cpv)}")


def main() -> None:
    p = argparse.ArgumentParser(description="SimApNALYTICS - Zuschlaege nach Anbieter")
    p.add_argument("--firma", help="Firmenname-Teilstring, z.B. ricoh")
    p.add_argument("--vergleich", action="store_true", help="Ricoh vs. Canon vergleichen")
    p.add_argument("--cpv", action="append", help="CPV-Code (mehrfach); Default: Druck/Kopier-CPVs")
    p.add_argument("--von", default="2024-07-01", help="Publikation ab YYYY-MM-DD (Default simap-Start)")
    p.add_argument("--bis", default=date.today().isoformat(), help="Publikation bis YYYY-MM-DD")
    args = p.parse_args()

    cpv = args.cpv or PRINT_CPV
    client = SimapClient()
    print(f"Zeitraum {args.von} bis {args.bis}  |  CPV: {', '.join(cpv)}")
    print("Lade Zuschlaege und Details (kann etwas dauern)…")

    if args.vergleich:
        ricoh, r_total = summarize(client, "ricoh", cpv, args.von, args.bis)
        canon, c_total = summarize(client, "canon", cpv, args.von, args.bis)
        print_awards("RICOH", ricoh, r_total)
        print_awards("CANON", canon, c_total)
        print("\n========== VERGLEICH ==========")
        print(f"Ricoh:  {len(ricoh):>3} Zuschlaege   CHF {r_total:>15,.2f}")
        print(f"Canon:  {len(canon):>3} Zuschlaege   CHF {c_total:>15,.2f}")
    elif args.firma:
        awards, total = summarize(client, args.firma, cpv, args.von, args.bis)
        print_awards(args.firma.upper(), awards, total)
    else:
        p.error("Bitte --firma NAME oder --vergleich angeben.")


if __name__ == "__main__":
    main()
