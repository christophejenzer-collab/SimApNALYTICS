"""Datenmodelle und Normalisierung der ECHTEN simap-v2-Felder.

Verifiziert anhand realer API-Antworten (Mai 2026):
- Projektsuche liefert nur Header (mehrsprachige Titel-Objekte, orderAddress).
- Zuschlagsdaten stehen in der Detail-Antwort unter dem Key "decision":
    decision.vendors[].vendorName / .price.price   -> Empfaenger + Summe
    decision.awardDecisionDate                     -> Zuschlagsdatum
    decision.numberOfSubmissions                   -> Anzahl Anbieter
- CPV: procurement.cpvCode.code (+ procurement.additionalCpvCodes[].code)
- Texte sind {de,en,fr,it}-Objekte -> per Sprache aufloesen.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


def _lang(val: Any, lang: str = "de") -> str | None:
    """Loest ein mehrsprachiges {de,en,fr,it}-Objekt auf einen String auf.
    Faellt auf andere Sprachen zurueck, falls die gewuenschte leer ist."""
    if val is None:
        return None
    if isinstance(val, str):
        return val.strip() or None
    if isinstance(val, dict):
        for key in (lang, "de", "fr", "it", "en"):
            v = val.get(key)
            if v:
                return str(v).strip()
    return None


@dataclass
class ProjectHeader:
    """Ein Treffer aus der Projektsuche (project-search)."""
    project_id: str | None
    publication_id: str | None
    project_number: str | None
    title: str | None
    project_type: str | None        # tender, ...
    project_sub_type: str | None    # service, construction, supply
    process_type: str | None        # open, selective, ...
    pub_type: str | None            # award, tender, ...
    publication_date: str | None
    proc_office: str | None
    canton: str | None

    @classmethod
    def from_raw(cls, r: dict[str, Any], lang: str = "de") -> "ProjectHeader":
        addr = r.get("orderAddress") or {}
        return cls(
            project_id=r.get("id"),
            publication_id=r.get("publicationId"),
            project_number=r.get("projectNumber"),
            title=_lang(r.get("title"), lang),
            project_type=r.get("projectType"),
            project_sub_type=r.get("projectSubType"),
            process_type=r.get("processType"),
            pub_type=r.get("pubType"),
            publication_date=r.get("publicationDate"),
            proc_office=_lang(r.get("procOfficeName"), lang),
            canton=addr.get("cantonId"),
        )

    @property
    def is_award(self) -> bool:
        return (self.pub_type or "").lower().startswith("award") or \
               (self.pub_type or "") == "direct_award"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Award:
    """Vollstaendiger Zuschlag = Header + decision-Block aus der Detail-Antwort.
    Genau das, was dich interessiert: wer, wann, wie viel, Zeitraum."""
    project_id: str | None
    publication_id: str | None
    project_number: str | None
    title: str | None
    canton: str | None
    proc_office: str | None
    award_companies: list[str]      # decision.vendors[].vendorName
    award_price: float | None       # Summe ueber vendors[].price.price
    award_currency: str | None
    award_date: str | None          # decision.awardDecisionDate
    nr_of_offers: int | None        # decision.numberOfSubmissions
    cpv: list[str]                  # cpvCode.code + additionalCpvCodes
    process_type: str | None
    publication_date: str | None
    project_start: str | None       # falls vorhanden (oft None bei Awards)
    project_end: str | None
    # Geschaetzte Vertragslaufzeit aus Beschreibungstext (HEURISTISCH)
    duration_main_months: int | None
    duration_optional_months: int | None
    duration_end_estimated: str | None       # Hauptlaufzeit -> ISO-Datum
    duration_end_max_estimated: str | None   # + alle Optionen -> ISO-Datum
    duration_confidence: str                 # "high"|"medium"|"low"|"none"
    duration_source: list[str]               # Quellen-Phrasen

    @classmethod
    def from_detail(cls, header: "ProjectHeader", detail: dict[str, Any],
                    lang: str = "de") -> "Award":
        proc = detail.get("procurement") or {}
        decision = detail.get("decision") or {}
        vendors = decision.get("vendors") or []

        companies, total = [], 0.0
        currency = None
        has_price = False
        for v in vendors:
            name = v.get("vendorName")
            if name:
                companies.append(str(name))
            p = (v.get("price") or {})
            if p.get("price") is not None:
                try:
                    total += float(p["price"])
                    has_price = True
                    currency = currency or p.get("currency")
                except (TypeError, ValueError):
                    pass

        cpv = []
        cv = (proc.get("cpvCode") or {}).get("code")
        if cv:
            cpv.append(str(cv))
        for ac in (proc.get("additionalCpvCodes") or []):
            if ac.get("code"):
                cpv.append(str(ac["code"]))

        # Vertragslaufzeit aus Beschreibungstext schaetzen (heuristisch)
        from .parsing.contract_duration import parse_duration
        desc_obj = proc.get("orderDescription")
        desc_text = _lang(desc_obj, lang)
        award_dt = decision.get("awardDecisionDate")
        dur = parse_duration(desc_text, award_dt)

        return cls(
            project_id=header.project_id,
            publication_id=header.publication_id,
            project_number=header.project_number,
            title=header.title or _lang(proc.get("orderDescription"), lang),
            canton=header.canton,
            proc_office=header.proc_office,
            award_companies=companies,
            award_price=total if has_price else None,
            award_currency=(currency or "").upper() or None,
            award_date=award_dt,
            nr_of_offers=decision.get("numberOfSubmissions"),
            cpv=cpv,
            process_type=header.process_type,
            publication_date=header.publication_date,
            project_start=proc.get("dateProjectStart") or detail.get("dateProjectStart"),
            project_end=proc.get("dateProjectEnd") or detail.get("dateProjectEnd"),
            duration_main_months=dur.main_months,
            duration_optional_months=dur.optional_months,
            duration_end_estimated=dur.explicit_end or dur.estimated_end,
            duration_end_max_estimated=dur.estimated_end_max,
            duration_confidence=dur.confidence,
            duration_source=dur.source_phrases,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
