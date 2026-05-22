"""Datenmodelle und Normalisierung der echten simap-Felder.

Award-Felder verifiziert anhand realer API-Antworten:
  award_companies, award_date, award_price, nr_of_offers,
  date_project_start, date_project_end, datetime_deadline, datetime_opening.
Da die v2-Projektsuche und die Detail-Antwort teils andere/zusaetzliche Felder
liefern, mappen wir defensiv ueber mehrere moegliche Namen.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


def _first(d: dict, *keys: str, default: Any = None) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, "", []):
            return d[k]
    return default


def _to_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


@dataclass
class Award:
    """Genau die Infos, die dich interessieren: Wer hat gewonnen, wann,
    fuer wie viel, und ueber welchen Zeitraum laeuft die Beschaffung."""
    project_id: str | None
    publication_id: str | None
    title: str | None
    canton: str | None
    proc_office: str | None
    award_companies: list[str]      # Zuschlagsempfaenger
    award_date: str | None          # Zuschlagsdatum
    award_price: float | None       # Zuschlagssumme
    nr_of_offers: int | None
    project_start: str | None       # Beschaffung Beginn
    project_end: str | None         # Beschaffung Ende / fertig bis
    submission_deadline: str | None # Eingabefrist (falls vorhanden)
    cpv: list[str]
    procedure: str | None
    is_wto: bool | None

    @classmethod
    def from_raw(cls, r: dict[str, Any]) -> "Award":
        companies = _first(r, "award_companies", "awardCompanies", "winners", default=[]) or []
        if isinstance(companies, str):
            companies = [companies]
        cpv = _first(r, "cpvCodes", "cpv", "cpcCode", default=[]) or []
        if isinstance(cpv, str):
            cpv = [c.strip() for c in cpv.split(",") if c.strip()]
        return cls(
            project_id=str(_first(r, "projectId", "project_id", "id", default="")) or None,
            publication_id=str(_first(r, "publicationId", "publication_id", "id_simap", default="")) or None,
            title=_first(r, "title", "projectTitle", "project_title"),
            canton=_first(r, "auth_canton", "canton", "orderAddressCanton"),
            proc_office=_first(r, "proc_office", "procOffice", "auth_activity", "procurementOffice"),
            award_companies=[str(c) for c in companies],
            award_date=_first(r, "award_date", "awardDate"),
            award_price=_to_float(_first(r, "award_price", "awardPrice")),
            nr_of_offers=_first(r, "nr_of_offers", "numberOfOffers"),
            project_start=_first(r, "date_project_start", "dateProjectStart", "projectStart"),
            project_end=_first(r, "date_project_end", "dateProjectEnd", "projectEnd"),
            submission_deadline=_first(r, "datetime_deadline", "offerDeadline", "submissionDeadline"),
            cpv=[str(c) for c in cpv],
            procedure=_first(r, "procedure", "procedureType", "processType"),
            is_wto=_first(r, "is_wto", "isWto", "wto"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Publication:
    """Allgemeine Publikation (Ausschreibung ODER Zuschlag) fuer breitere Analysen."""
    project_id: str | None
    publication_id: str | None
    title: str | None
    pub_type: str | None
    canton: str | None
    proc_office: str | None
    cpv: list[str]
    date: str | None
    award_companies: list[str]
    award_date: str | None
    award_price: float | None

    @classmethod
    def from_raw(cls, r: dict[str, Any]) -> "Publication":
        companies = _first(r, "award_companies", "awardCompanies", default=[]) or []
        if isinstance(companies, str):
            companies = [companies]
        cpv = _first(r, "cpvCodes", "cpv", default=[]) or []
        if isinstance(cpv, str):
            cpv = [c.strip() for c in cpv.split(",") if c.strip()]
        return cls(
            project_id=str(_first(r, "projectId", "project_id", default="")) or None,
            publication_id=str(_first(r, "publicationId", "publication_id", default="")) or None,
            title=_first(r, "title", "projectTitle"),
            pub_type=_first(r, "pubType", "newestPubType", "publicationType", "category"),
            canton=_first(r, "auth_canton", "canton", "orderAddressCanton"),
            proc_office=_first(r, "proc_office", "procOffice", "procurementOffice"),
            cpv=[str(c) for c in cpv],
            date=_first(r, "date", "newestPublicationDate", "publicationDate"),
            award_companies=[str(c) for c in companies],
            award_date=_first(r, "award_date", "awardDate"),
            award_price=_to_float(_first(r, "award_price", "awardPrice")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
