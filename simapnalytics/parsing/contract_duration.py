"""Heuristisches Parsing der Vertragslaufzeit aus simap-Beschreibungstexten.

Wichtig: das ist eine SCHAETZUNG, nicht zuverlaessig. Wir markieren das
Ergebnis entsprechend. simap hat KEINE strukturierten Laufzeitfelder.

Erkennt Hauptlaufzeit (Jahre/Monate) und Verlaengerungs-Optionen aus
deutschem und franzoesischem Text. Bei Mehrdeutigkeit wird der wahrschein-
lichste Wert genommen; Quellen-Phrase wird zur Nachvollziehbarkeit
mitgeliefert.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from datetime import date
from typing import Any

# Zahlworte -> Zahl (deutsch + franzoesisch). Wir bleiben pragmatisch klein.
NUM_WORDS = {
    # de
    "ein": 1, "eine": 1, "einem": 1, "einer": 1, "einen": 1,
    "zwei": 2, "drei": 3, "vier": 4, "fuenf": 5, "fünf": 5,
    "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10,
    # fr
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4,
    "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
}

# Multiplikator-Worte fuer Verlaengerungen
MULTIPLIER_WORDS = {
    # de
    "einmal": 1, "zweimal": 2, "dreimal": 3, "viermal": 4,
    # fr
    "une fois": 1, "deux fois": 2, "trois fois": 3,
}


def _strip_html(text: str) -> str:
    """HTML-Tags und HTML-Entities aus Text loeschen."""
    if not text:
        return ""
    t = re.sub(r"<[^>]+>", " ", text)
    t = (t.replace("&nbsp;", " ").replace("&amp;", "&")
          .replace("&lt;", "<").replace("&gt;", ">"))
    return re.sub(r"\s+", " ", t).strip()


def _num(token: str) -> int | None:
    """Konvertiert '5' oder 'fuenf' -> 5."""
    token = token.lower().strip()
    if token.isdigit():
        return int(token)
    return NUM_WORDS.get(token)


def _to_months(value: int, unit: str) -> int:
    unit = unit.lower()
    # Jahre (de) / années / ans (fr)
    if unit.startswith(("jahr", "ann", "an")):
        return value * 12
    # Monate (de) / mois (fr)
    if unit.startswith(("mona", "mois")):
        return value
    return 0


# Hauptlaufzeit-Patterns: erfassen <Zahl/Wort> <Einheit>
# Deutsch
_PAT_MAIN_DE = re.compile(
    r"(?:Laufzeit|Vertragsdauer|Vertragslaufzeit|Rahmenvertrag(?:s)?dauer)"
    r"\s+(?:von|über|ueber|betr(?:ä|ae)gt)?\s*"
    r"(\d+|ein|eine|einem|einer|einen|zwei|drei|vier|fünf|fuenf|sechs|sieben|acht|neun|zehn)"
    r"\s+(Jahr(?:e|en|es)?|Monat(?:e|en|s)?)",
    re.IGNORECASE,
)
# Alternative DE: "Rahmenvertrag (über) X Jahre"
_PAT_MAIN_DE2 = re.compile(
    r"Rahmen(?:vertrag|laufzeit)?\s+(?:über|ueber|von)?\s*"
    r"(\d+|ein|eine|zwei|drei|vier|fünf|fuenf|sechs|sieben|acht|neun|zehn)"
    r"\s+(Jahr(?:e|en|es)?|Monat(?:e|en|s)?)",
    re.IGNORECASE,
)
# Franzoesisch
_PAT_MAIN_FR = re.compile(
    r"(?:dur(?:é|e)e\s+(?:du\s+)?(?:contrat|contractuelle|de\s+l[''']accord(?:[- ]cadre)?)|"
    r"contrat(?:[- ]cadre)?\s+d['']une\s+dur(?:é|e)e)"
    r"\s+(?:de\s+)?"
    r"(\d+|un|une|deux|trois|quatre|cinq|six|sept|huit|neuf|dix)"
    r"\s+(an(?:s|n(?:é|e)es?)?|ann(?:é|e)es?|mois)",
    re.IGNORECASE,
)

# Optionen / Verlaengerungen
_PAT_OPT_DE = re.compile(
    r"(?:kann\s+|um\s+|optional\s+)?(einmal|zweimal|dreimal|viermal)?\s*"
    r"(?:um\s+)?(\d+|ein|eine|zwei|drei|vier|fünf|fuenf|sechs|sieben|acht|neun|zehn)"
    r"\s+(Jahr(?:e|en|es)?|Monat(?:e|en|s)?)\s+(?:verlängert|verlangert|erweitert)",
    re.IGNORECASE,
)
_PAT_OPT_FR = re.compile(
    r"prolong(?:é|e)e?\s+(?:de\s+)?"
    r"(\d+|un|une|deux|trois|quatre|cinq|six|sept|huit|neuf|dix)"
    r"\s+(an(?:s|n(?:é|e)es?)?|ann(?:é|e)es?|mois)",
    re.IGNORECASE,
)

# Konkrete Enddaten (bis 31.12.2030, jusqu'au 2030, etc.)
_PAT_END_DE = re.compile(
    r"(?:bis|laufend\s+bis|Ende\s+der\s+Laufzeit\s*:?)\s+"
    r"(?:(\d{1,2})[./](\d{1,2})[./])?(\d{4})",
    re.IGNORECASE,
)
_PAT_END_FR = re.compile(
    r"jusqu['']au?\s+(?:(\d{1,2})[./](\d{1,2})[./])?(\d{4})",
    re.IGNORECASE,
)


@dataclass
class ContractDurationEstimate:
    main_months: int | None              # Hauptlaufzeit in Monaten
    optional_months: int | None          # Summe aller Verlaengerungs-Optionen
    estimated_end: str | None            # Geschaetztes regulaeres Ende (ISO)
    estimated_end_max: str | None        # Mit Optionen ausgeschoepft (ISO)
    explicit_end: str | None             # Wenn ein konkretes Datum genannt war
    source_phrases: list[str]            # Phrasen, die zur Schaetzung fuehrten
    confidence: str                      # "high" | "medium" | "low" | "none"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_duration(raw_description: str | None, base_date: str | None = None
                   ) -> ContractDurationEstimate:
    """Parst Vertragslaufzeit aus dem Beschreibungstext.

    base_date: Datum, ab dem die Laufzeit gerechnet wird (idealerweise das
    Zuschlagsdatum). Format YYYY-MM-DD.

    Liefert eine Schaetzung mit Quellen-Phrasen und Confidence-Level.
    """
    text = _strip_html(raw_description or "")
    if not text:
        return ContractDurationEstimate(None, None, None, None, None, [], "none")

    main_months: int | None = None
    optional_months: int = 0
    sources: list[str] = []

    # Hauptlaufzeit: DE-Hauptmuster bevorzugt, dann FR, dann DE-Alternative
    for pat in (_PAT_MAIN_DE, _PAT_MAIN_FR, _PAT_MAIN_DE2):
        m = pat.search(text)
        if m:
            n = _num(m.group(1))
            if n:
                main_months = _to_months(n, m.group(2))
                sources.append(m.group(0).strip())
                break

    # Optionen: alle Treffer summieren
    for pat in (_PAT_OPT_DE, _PAT_OPT_FR):
        for m in pat.finditer(text):
            # Bei DE haben wir optional Multiplikator (einmal/zweimal) + Zahl
            if pat is _PAT_OPT_DE:
                mult = MULTIPLIER_WORDS.get((m.group(1) or "").lower(), 1)
                n = _num(m.group(2))
                unit = m.group(3)
            else:
                mult = 1
                n = _num(m.group(1))
                unit = m.group(2)
            if n:
                optional_months += mult * _to_months(n, unit)
                sources.append(m.group(0).strip())

    # Konkretes Enddatum (selten, aber wertvoll)
    explicit_end = None
    for pat in (_PAT_END_DE, _PAT_END_FR):
        m = pat.search(text)
        if m:
            day = m.group(1) or "31"
            month = m.group(2) or "12"
            year = m.group(3)
            try:
                explicit_end = date(int(year), int(month), int(day)).isoformat()
                sources.append(m.group(0).strip())
                break
            except ValueError:
                pass

    # Confidence-Heuristik
    confidence = "none"
    if main_months and sources:
        confidence = "high" if "vertragsdauer" in " ".join(sources).lower() \
            or "laufzeit" in " ".join(sources).lower() \
            or "durée" in " ".join(sources).lower() \
            else "medium"
    elif explicit_end:
        confidence = "medium"
    elif sources:
        confidence = "low"

    # Enddaten berechnen, wenn base_date vorhanden
    est_end = None
    est_max = None
    if base_date and main_months:
        try:
            d = date.fromisoformat(base_date)
            est_end = _add_months(d, main_months).isoformat()
            est_max = _add_months(d, main_months + optional_months).isoformat()
        except ValueError:
            pass

    return ContractDurationEstimate(
        main_months=main_months,
        optional_months=optional_months or None,
        estimated_end=est_end,
        estimated_end_max=est_max if optional_months else None,
        explicit_end=explicit_end,
        source_phrases=sources,
        confidence=confidence,
    )


def _add_months(d: date, months: int) -> date:
    """Addiert Monate auf ein Datum (saubere Monatsarithmetik)."""
    m_idx = d.month - 1 + months
    year = d.year + m_idx // 12
    month = m_idx % 12 + 1
    # Tag auf Monatsende clampen, falls Zieltag im Zielmonat nicht existiert
    day = min(d.day, _days_in_month(year, month))
    return date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    if month in (1, 3, 5, 7, 8, 10, 12):
        return 31
    if month in (4, 6, 9, 11):
        return 30
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    return 29 if leap else 28
