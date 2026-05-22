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
