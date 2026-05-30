"""CPV-Katalog: vordefinierte Kategorien fuer einfache Auswahl im UI.

Quelle: offizielle CPV-Klassifikation 2008 (EU). Liste deckt typische
Domaenen fuer simap-Beschaffungen ab und kann beliebig erweitert werden.
"""
from __future__ import annotations

# Dict: Kategoriename -> Liste von (Code, Beschreibung)
CPV_CATEGORIES: dict[str, list[tuple[str, str]]] = {
    "Architektur (71200000)": [
        ("71200000", "Dienstleistungen von Architekturbüros"),
        ("71210000", "Beratungsdienste von Architekten"),
        ("71220000", "Architekturentwurf"),
        ("71221000", "Architekturleistungen für Gebäude"),
        ("71222000", "Architekturleistungen für Außenanlagen"),
        ("71223000", "Architekturleistungen für raumbildende Ausbauten"),
        ("71230000", "Organisation Architektenwettbewerb"),
        ("71240000", "Architektur-/Ingenieurbüros, planungsbezogene Leistungen"),
        ("71250000", "Architektur-/Ingenieurbüros, Vermessung"),
    ],
    "Ingenieurleistungen (71300000)": [
        ("71300000", "Dienstleistungen von Ingenieurbüros"),
        ("71310000", "Technische Beratungs- und Konsultationsleistungen"),
        ("71311000", "Beratung im Bauingenieurwesen"),
        ("71313000", "Beratung im Umweltingenieurwesen"),
        ("71320000", "Planungsleistungen im Ingenieurwesen"),
        ("71321000", "Technische Planung Mechanik/Elektrik für Gebäude"),
        ("71322000", "Technische Planung im Tief-/Hochbau"),
        ("71330000", "Verschiedene Ingenieurleistungen"),
        ("71356000", "Technische Dienstleistungen"),
    ],
    "Bauarbeiten allgemein (45000000)": [
        ("45000000", "Bauarbeiten"),
        ("45100000", "Baustellenvorbereitung"),
        ("45200000", "Komplett-/Teilbauarbeiten, Tiefbau"),
        ("45210000", "Hochbauarbeiten"),
        ("45211000", "Bau von Mehrfamilien- und Einfamilienhäusern"),
        ("45214000", "Bauarbeiten Bildungs-/Forschungsgebäude"),
        ("45215000", "Bauarbeiten Gesundheitsgebäude"),
        ("45220000", "Ingenieur- und Hochbauten"),
        ("45221000", "Bauarbeiten Brücken/Tunnel/Schächte"),
    ],
    "Strassenbau/Tiefbau (45230000)": [
        ("45230000", "Bauarbeiten für Rohrleitungen, Strassen, Eisenbahn"),
        ("45233000", "Strassenbau"),
        ("45233100", "Bauarbeiten Strassen/Autobahnen"),
        ("45233140", "Strassenbauarbeiten"),
        ("45233200", "Verschiedene Strassenbelagsarbeiten"),
        ("45232000", "Hilfsarbeiten für Rohrleitungen/Kabel"),
        ("45232400", "Bau von Abwasserkanälen"),
        ("45232450", "Bau von Entwässerungsanlagen"),
    ],
    "Gebäudetechnik / HLKS (45300000)": [
        ("45300000", "Bauinstallationsarbeiten"),
        ("45310000", "Elektroinstallationsarbeiten"),
        ("45317000", "Sonstige Elektroinstallationsarbeiten"),
        ("45330000", "Klempner-/Installateurarbeiten"),
        ("45331000", "Heizungs-, Lüftungs-, Klimainstallation"),
        ("45332000", "Klempner-/Abwasserinstallation"),
        ("45333000", "Gasinstallation"),
    ],
    "IT-Dienstleistungen (72000000)": [
        ("72000000", "IT-Dienste: Beratung, Software, Internet, Support"),
        ("72100000", "Beratung im Hardware-Bereich"),
        ("72200000", "Software-Programmierung und -Beratung"),
        ("72220000", "Systemberatung"),
        ("72300000", "Datendienste"),
        ("72500000", "Computerbezogene Dienste"),
        ("72600000", "Computer-Support, Beratung"),
        ("48000000", "Softwarepakete und IT-Systeme"),
    ],
    "Drucken / Kopieren (30120000)": [
        ("30120000", "Fotokopier- und Offsetdruckgeräte"),
        ("30121100", "Fotokopierer"),
        ("30232100", "Drucker und Plotter"),
        ("30232110", "Laserdrucker"),
        ("30232130", "Farbgrafikdrucker"),
        ("30232150", "Tintenstrahldrucker"),
        ("79800000", "Druckereidienste"),
        ("50313000", "Wartung/Reparatur Kopiergeräte"),
    ],
    "Beratung / Consulting (79000000)": [
        ("79400000", "Unternehmens-/Managementberatung"),
        ("79410000", "Unternehmensberatung"),
        ("79411000", "Allgemeine Unternehmensberatung"),
        ("79412000", "Finanzberatung"),
        ("79420000", "Managementberatung"),
        ("79421000", "Projektmanagement (ausgenommen Baustellenüberwachung)"),
    ],
    "Reinigung / Unterhalt (90000000)": [
        ("90910000", "Reinigungsdienste"),
        ("90911000", "Reinigung von Wohnungen, Gebäuden, Fenstern"),
        ("90911200", "Gebäudereinigung"),
        ("90919000", "Reinigung von Büro-, Schul- und Bürogeräten"),
        ("90920000", "Hygiene-Dienstleistungen"),
    ],
    "Medizinische Geräte (33000000)": [
        ("33000000", "Medizinische Geräte und Arzneimittel"),
        ("33100000", "Medizinische Geräte"),
        ("33140000", "Medizinische Verbrauchsartikel"),
        ("33600000", "Pharmazeutische Erzeugnisse"),
        ("38000000", "Laborgeräte, optische und Präzisionsgeräte"),
    ],
}


def codes_for(category: str) -> list[str]:
    """Liefert die CPV-Codes (8-stellig) einer Kategorie."""
    return [c for c, _ in CPV_CATEGORIES.get(category, [])]


def all_codes_with_labels() -> list[tuple[str, str, str]]:
    """Flache Liste: (kategorie, code, label) – fuer Detail-Auswahl."""
    out: list[tuple[str, str, str]] = []
    for cat, items in CPV_CATEGORIES.items():
        for code, label in items:
            out.append((cat, code, label))
    return out
