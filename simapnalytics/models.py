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

    @property
    def is_tender(self) -> bool:
        pt = (self.pub_type or "").lower()
        return pt in ("tender", "tender_competition", "tender_study_contract")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Tender:
    """Eine offene Ausschreibung mit Eingabefrist und Vertragslaufzeit.

    Datumsfelder kommen aus dem Detail-Block `dates`, Vertragsdaten aus
    `procurement.contractPeriod` (strukturiert, hart) bzw. aus dem
    `orderDescription`-Text als Fallback.
    """
    project_id: str | None
    publication_id: str | None
    project_number: str | None
    title: str | None
    canton: str | None
    proc_office: str | None
    cpv: list[str]
    process_type: str | None
    pub_type: str | None
    publication_date: str | None
    initial_publication_date: str | None
    offer_deadline: str | None              # dates.offerDeadline
    documents_available_until: str | None   # dates.documentsAvailable.dateRange[1]
    select_participants_date: str | None    # selektiv: Auswahl Teilnehmer
    offer_validity_until: str | None        # dates.offerValidityDeadlineDate
    # Vertragslaufzeit: bevorzugt strukturiert, sonst Text-Heuristik
    contract_start: str | None
    contract_end: str | None
    contract_days: int | None
    can_be_extended: str | None             # "yes"/"no"
    contract_source: str                    # "structured" | "text" | "none"

    @classmethod
    def from_detail(cls, header: "ProjectHeader", detail: dict[str, Any],
                    lang: str = "de") -> "Tender":
        proc = detail.get("procurement") or {}
        dates = detail.get("dates") or {}
        info = detail.get("project-info") or {}

        # Titel: Header kann None sein -> Detail nutzen
        title = header.title or _lang(info.get("title"), lang)

        # CPV
        cpv = []
        cv = (proc.get("cpvCode") or {}).get("code")
        if cv:
            cpv.append(str(cv))
        for ac in (proc.get("additionalCpvCodes") or []):
            if ac.get("code"):
                cpv.append(str(ac["code"]))

        # Helper fuer evtl. verschachtelte Datumsfelder
        def _dt(obj: Any) -> str | None:
            if not obj:
                return None
            if isinstance(obj, str):
                return obj
            if isinstance(obj, dict):
                return obj.get("dateTime") or obj.get("date")
            return None

        docs_until = None
        docs = dates.get("documentsAvailable") or {}
        rng = docs.get("dateRange") or []
        if len(rng) >= 2:
            docs_until = rng[1]

        # Vertragslaufzeit: strukturiert bevorzugt
        contract_start = None
        contract_end = None
        source = "none"
        cp = proc.get("contractPeriod") or {}
        cp_range = cp.get("dateRange") or []
        if len(cp_range) >= 2 and cp_range[0] and cp_range[1]:
            contract_start = cp_range[0]
            contract_end = cp_range[1]
            source = "structured"
        else:
            # Fallback: Heuristik aus Beschreibungstext
            from .parsing.contract_duration import parse_duration
            base = header.publication_date
            dur = parse_duration(_lang(proc.get("orderDescription"), lang), base)
            if dur.estimated_end or dur.explicit_end:
                contract_end = dur.explicit_end or dur.estimated_end
                contract_start = base
                source = "text"

        return cls(
            project_id=header.project_id,
            publication_id=header.publication_id,
            project_number=header.project_number,
            title=title,
            canton=header.canton,
            proc_office=header.proc_office,
            cpv=cpv,
            process_type=header.process_type,
            pub_type=header.pub_type,
            publication_date=dates.get("publicationDate") or header.publication_date,
            initial_publication_date=dates.get("initialPublicationDate"),
            offer_deadline=_dt(dates.get("offerDeadline")),
            documents_available_until=docs_until,
            select_participants_date=_dt(dates.get("selectParticipants")),
            offer_validity_until=dates.get("offerValidityDeadlineDate"),
            contract_start=contract_start,
            contract_end=contract_end,
            contract_days=proc.get("contractDays"),
            can_be_extended=proc.get("canContractBeExtended"),
            contract_source=source,
        )

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
