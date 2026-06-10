"""HTTP-Client fuer die OEFFENTLICHE simap-API (anonym, kein Login).

Endpunkte und Parameter verifiziert anhand der offiziellen Doku
(simap.ch/api-doc) und des Open-Source-Referenzprojekts Digilac/simap-mcp (MIT).

Basis: https://www.simap.ch/api
Suche: GET /publications/v2/project/project-search  (mind. 1 Filter Pflicht)
Detail: GET /publications/v1/project/{projectId}/publication-details/{publicationId}
"""
from __future__ import annotations

import time
from typing import Any, Iterator

import requests

from ..auth import SimapAuth
from ..config import SimapConfig

# Tool-Parametername -> echter simap-API-Parametername
PARAM_MAP = {
    "search": "search",
    "publicationFrom": "newestPublicationFrom",
    "publicationUntil": "newestPublicationUntil",
    "projectSubTypes": "projectSubTypes",
    "cantons": "orderAddressCantons",
    "processTypes": "processTypes",
    "pubTypes": "newestPubTypes",
    "cpvCodes": "cpvCodes",
    "bkpCodes": "bkpCodes",
    "issuedByOrganizations": "issuedByOrganizations",
    "lastItem": "lastItem",
}

# Publikationstypen, die einen Zuschlagsempfaenger tragen
AWARD_PUB_TYPES = ["award_tender", "award_study_contract", "award_competition", "direct_award"]


class SimapClient:
    """Anonymer simap-Client. authenticate=True nur fuer geschuetzte Aktionen."""

    def __init__(
        self,
        config: SimapConfig | None = None,
        auth: SimapAuth | None = None,
        authenticate: bool = False,
    ) -> None:
        self.cfg = config or SimapConfig()
        self.authenticate = authenticate
        self.auth = auth if auth is not None else (SimapAuth(self.cfg) if authenticate else None)
        self.session = requests.Session()
        self._last_call = 0.0

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/json", "User-Agent": "simapnalytics/0.4"}
        if self.authenticate and self.auth is not None:
            h["Authorization"] = f"Bearer {self.auth.get_access_token()}"
        return h

    def _throttle(self) -> None:
        gap = 60.0 / max(self.cfg.rate_limit_per_min, 1)
        wait = gap - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = path if path.startswith("http") else f"{self.cfg.api_base_url}{path}"
        last_err: Exception | None = None
        for attempt in range(self.cfg.max_retries):
            self._throttle()
            try:
                r = self.session.get(url, headers=self._headers(), params=params,
                                     timeout=self.cfg.timeout_s)
                if r.status_code in (429, 502, 503, 504):
                    time.sleep(2 ** attempt)
                    continue
                r.raise_for_status()
                return r.json() if r.content else {}
            except requests.RequestException as e:
                last_err = e
                time.sleep(2 ** attempt)
        raise RuntimeError(f"GET fehlgeschlagen: {url}") from last_err

    # --- Projektsuche -----------------------------------------------------

    def search_projects(
        self,
        *,
        search: str | None = None,
        publication_from: str | None = None,   # YYYY-MM-DD
        publication_until: str | None = None,
        project_sub_types: list[str] | None = None,  # z.B. ["construction"]
        cantons: list[str] | None = None,            # z.B. ["BE"]
        process_types: list[str] | None = None,      # z.B. ["open"]
        pub_types: list[str] | None = None,          # z.B. AWARD_PUB_TYPES
        cpv_codes: list[str] | None = None,          # 8-stellig
        bkp_codes: list[str] | None = None,
        lang: str = "de",
        max_pages: int = 50,
    ) -> Iterator[dict[str, Any]]:
        """Sucht Projekte/Publikationen. Folgt der Cursor-Paginierung (lastItem).

        Liefert einzelne Projekt-Dicts (Generator). Mindestens ein Filter noetig.
        """
        tool_params: dict[str, Any] = {"search": search,
                                       "publicationFrom": publication_from,
                                       "publicationUntil": publication_until,
                                       "projectSubTypes": project_sub_types,
                                       "cantons": cantons,
                                       "processTypes": process_types,
                                       "pubTypes": pub_types,
                                       "cpvCodes": cpv_codes,
                                       "bkpCodes": bkp_codes}
        # Auf echte API-Namen mappen, leere Werte verwerfen
        base: dict[str, Any] = {}
        for tool_key, val in tool_params.items():
            if val:
                base[PARAM_MAP[tool_key]] = val
        base["lang"] = lang
        if not any(k for k in base if k != "lang"):
            raise ValueError("Mindestens ein Suchfilter ist erforderlich.")

        last_item: str | None = None
        for _ in range(max_pages):
            params = dict(base)
            if last_item:
                params[PARAM_MAP["lastItem"]] = last_item
            data = self._get(self.cfg.path_project_search, params=params)
            projects = data.get("projects") or []
            if not projects:
                break
            yield from projects
            pagination = data.get("pagination") or {}
            last_item = pagination.get("lastItem")
            if not last_item:
                break

    def get_publication_details(self, project_id: str, publication_id: str,
                                lang: str = "de") -> dict[str, Any]:
        path = self.cfg.path_publication_details.format(
            project_id=project_id, publication_id=publication_id)
        return self._get(path, params={"lang": lang})

    def get_project_header(self, project_id: str, lang: str = "de") -> dict[str, Any]:
        path = self.cfg.path_project_header.format(project_id=project_id)
        return self._get(path, params={"lang": lang})

    # --- High-Level: Zuschlaege mit allen Details -------------------------

    def find_awards(
        self,
        *,
        search: str | None = None,
        publication_from: str | None = None,
        publication_until: str | None = None,
        project_sub_types: list[str] | None = None,
        cantons: list[str] | None = None,
        cpv_codes: list[str] | None = None,
        lang: str = "de",
        max_results: int = 200,
    ):
        """Sucht Zuschlags-Publikationen und laedt fuer jede die Detaildaten
        (Empfaenger, Datum, Summe, Anbieterzahl) nach.

        Liefert fertige Award-Objekte (Generator). Filtert serverseitig auf
        Award-Typen und client-seitig zur Sicherheit nochmal auf is_award.
        """
        from ..models import ProjectHeader, Award  # lokal: Vermeidet Zyklus

        headers = self.search_projects(
            search=search,
            publication_from=publication_from,
            publication_until=publication_until,
            project_sub_types=project_sub_types,
            cantons=cantons,
            cpv_codes=cpv_codes,
            pub_types=AWARD_PUB_TYPES,
            lang=lang,
        )
        n = 0
        for raw in headers:
            h = ProjectHeader.from_raw(raw, lang)
            if not h.is_award or not h.project_id or not h.publication_id:
                continue
            try:
                detail = self.get_publication_details(h.project_id, h.publication_id, lang)
            except RuntimeError:
                continue
            award = Award.from_detail(h, detail, lang)
            if not award.award_companies:
                continue
            yield award
            n += 1
            if n >= max_results:
                break

    def find_tenders(
        self,
        *,
        search: str | None = None,
        publication_from: str | None = None,
        publication_until: str | None = None,
        project_sub_types: list[str] | None = None,
        cantons: list[str] | None = None,
        cpv_codes: list[str] | None = None,
        only_open: bool = True,
        lang: str = "de",
        max_results: int = 200,
    ):
        """Sucht offene Ausschreibungen (Tender) und laedt Detaildaten nach.

        Liefert Tender-Objekte (Generator).
        only_open=True: filtert clientseitig auf Ausschreibungen, deren
        Eingabefrist noch in der Zukunft liegt.
        """
        from datetime import datetime
        from ..models import ProjectHeader, Tender

        headers = self.search_projects(
            search=search,
            publication_from=publication_from,
            publication_until=publication_until,
            project_sub_types=project_sub_types,
            cantons=cantons,
            cpv_codes=cpv_codes,
            pub_types=["tender"],
            lang=lang,
        )
        now = datetime.now().astimezone()
        n = 0
        for raw in headers:
            h = ProjectHeader.from_raw(raw, lang)
            if not h.is_tender or not h.project_id or not h.publication_id:
                continue
            try:
                detail = self.get_publication_details(h.project_id, h.publication_id, lang)
            except RuntimeError:
                continue
            t = Tender.from_detail(h, detail, lang)
            if only_open and t.offer_deadline:
                try:
                    dl = datetime.fromisoformat(t.offer_deadline)
                    if dl.tzinfo is None:
                        # Vergleich tz-naive vs tz-aware vermeiden
                        if dl < now.replace(tzinfo=None):
                            continue
                    elif dl < now:
                        continue
                except ValueError:
                    pass
            yield t
            n += 1
            if n >= max_results:
                break

    def find_awards_filtered(
        self,
        *,
        company_terms: list[str] | None = None,
        office_terms: list[str] | None = None,
        cpv_codes: list[str] | None = None,
        search: str | None = None,
        publication_from: str | None = None,
        publication_until: str | None = None,
        cantons: list[str] | None = None,
        project_sub_types: list[str] | None = None,
        lang: str = "de",
        scan_limit: int = 3000,
        progress_callback=None,
    ):
        """Findet Zuschlaege gefiltert nach Empfaenger UND/ODER Vergeber.

        Optimierung: Vergeber-Filter laeuft auf Header (kein Detail-Call noetig).
        Empfaenger-Filter braucht Detail. Wenn beides gesetzt: erst Vergeber
        filtern, dann Detail laden, dann Empfaenger pruefen -> minimiert
        API-Calls drastisch.

        Match jeweils per Teilstring (case-insensitiv).
        scan_limit: max. gescannte Header (Schutz vor Endlos-Last).
        progress_callback(scanned, hits): optionaler Fortschritts-Hook,
        wird nach jedem gescannten Header aufgerufen.
        """
        from ..models import ProjectHeader, Award

        company_low = [t.lower() for t in (company_terms or []) if t.strip()]
        office_low = [t.lower() for t in (office_terms or []) if t.strip()]
        if not company_low and not office_low:
            raise ValueError("Mindestens company_terms ODER office_terms angeben.")

        headers = self.search_projects(
            search=search,
            publication_from=publication_from,
            publication_until=publication_until,
            project_sub_types=project_sub_types,
            cantons=cantons,
            cpv_codes=cpv_codes,
            pub_types=AWARD_PUB_TYPES,
            lang=lang,
        )

        scanned = 0
        hits = 0
        for raw in headers:
            scanned += 1
            if scanned > scan_limit:
                break
            h = ProjectHeader.from_raw(raw, lang)
            if not h.is_award or not h.project_id or not h.publication_id:
                if progress_callback:
                    progress_callback(scanned, hits)
                continue
            # Vergeber-Filter direkt auf Header (schnell)
            if office_low:
                office_text = (h.proc_office or "").lower()
                if not any(t in office_text for t in office_low):
                    if progress_callback:
                        progress_callback(scanned, hits)
                    continue
            # Detail nur wenn Header-Filter passt
            try:
                detail = self.get_publication_details(
                    h.project_id, h.publication_id, lang)
            except RuntimeError:
                if progress_callback:
                    progress_callback(scanned, hits)
                continue
            award = Award.from_detail(h, detail, lang)
            if not award.award_companies:
                if progress_callback:
                    progress_callback(scanned, hits)
                continue
            # Empfaenger-Filter auf Detail
            if company_low:
                hay = " ".join(award.award_companies).lower()
                if not any(t in hay for t in company_low):
                    if progress_callback:
                        progress_callback(scanned, hits)
                    continue
            hits += 1
            if progress_callback:
                progress_callback(scanned, hits)
            yield award

    def find_awards_by_company(
        self,
        company_terms: list[str],
        *,
        cpv_codes: list[str] | None = None,
        search: str | None = None,
        publication_from: str | None = None,
        publication_until: str | None = None,
        cantons: list[str] | None = None,
        project_sub_types: list[str] | None = None,
        lang: str = "de",
        scan_limit: int = 2000,
    ):
        """Findet Zuschlaege, deren Empfaenger einen der company_terms enthaelt.

        Strategie: serverseitig per CPV/Suche/Zeitraum vorfiltern, Details laden,
        dann clientseitig nach Firmenname (Teilstring, case-insensitive) filtern.

        company_terms: z.B. ["ricoh"] oder ["canon"]. Match, wenn EIN Term in
        IRGENDEINEM award_company als Teilstring vorkommt.
        scan_limit: Obergrenze gescannter Zuschlaege (schuetzt vor Endlos-Last).

        Liefert (Award)-Generator.
        """
        terms = [t.lower() for t in company_terms if t.strip()]
        scanned = 0
        for award in self.find_awards(
            search=search,
            publication_from=publication_from,
            publication_until=publication_until,
            cantons=cantons,
            cpv_codes=cpv_codes,
            project_sub_types=project_sub_types,
            lang=lang,
            max_results=scan_limit,
        ):
            scanned += 1
            hay = " ".join(award.award_companies).lower()
            if any(t in hay for t in terms):
                yield award
            if scanned >= scan_limit:
                break
