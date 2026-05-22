"""Zentrale Konfiguration fuer das simap-Analyse-Tool.

Auth-Werte stammen aus dem offiziellen "Quick Guide Authorisation Code Flow"
(simap.ch, Stand Mai 2025): OpenID Connect / Keycloak, Authorization Code Flow
mit PKCE. 2FA ist Pflicht und an einen echten User gebunden.

Vor dem ersten Lauf setzen:
  SIMAP_CLIENT_ID      -> aus dem genehmigten API-Client-Antrag
  SIMAP_REDIRECT_URI   -> exakt eine der beim Antrag konfigurierten Redirect-URIs
  (optional) SIMAP_CLIENT_SECRET, falls dein Client "confidential" ist
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


# Realm-Basis laut Quick Guide. Fuer INT (Testumgebung) auf int.simap.ch wechseln.
_REALM_BASE_PROD = "https://www.simap.ch/auth/realms/simap"
_REALM_BASE_INT = "https://int.simap.ch/auth/realms/simap"


@dataclass
class SimapConfig:
    # Umgebung: "prod" oder "int" (Integration/Test fuer die Entwicklung)
    environment: str = os.getenv("SIMAP_ENV", "int")

    # --- API-Basis (oeffentliche API, anonym nutzbar) ---
    api_base_url: str = os.getenv("SIMAP_API_BASE", "https://www.simap.ch/api")

    # --- Echte Endpunkt-Pfade (verifiziert via api-doc + Digilac/simap-mcp) ---
    path_project_search: str = "/publications/v2/project/project-search"
    path_publication_details: str = (
        "/publications/v1/project/{project_id}/publication-details/{publication_id}"
    )
    path_project_header: str = "/publications/v2/project/{project_id}/project-header"
    path_past_publications: str = "/publications/v1/publication/{publication_id}/past-publications"
    path_cpv_search: str = "/codes/v1/cpv/search"

    # --- OAuth2 / OIDC ---
    client_id: str = field(default_factory=lambda: os.getenv("SIMAP_CLIENT_ID", ""))
    client_secret: str | None = field(default_factory=lambda: os.getenv("SIMAP_CLIENT_SECRET"))
    redirect_uri: str = field(
        default_factory=lambda: os.getenv("SIMAP_REDIRECT_URI", "http://localhost:8765/callback")
    )
    scope: str = os.getenv("SIMAP_SCOPE", "openid profile")
    # Fuer langlebigen Refresh Token zusaetzlich "offline_access" anfragen:
    #   SIMAP_SCOPE="openid profile offline_access"
    # Falls simap dir Client Credentials (M2M) freischaltet -> True setzen:
    use_client_credentials: bool = os.getenv("SIMAP_M2M", "0") == "1"
    token_cache_path: str = os.getenv("SIMAP_TOKEN_CACHE", ".simap_token.json")

    # --- Netzwerk ---
    timeout_s: float = 30.0
    max_retries: int = 3
    rate_limit_per_min: int = 60

    @property
    def _realm_base(self) -> str:
        return _REALM_BASE_INT if self.environment == "int" else _REALM_BASE_PROD

    @property
    def oidc_discovery_url(self) -> str:
        return f"{self._realm_base}/.well-known/openid-configuration"

    @property
    def auth_endpoint_fallback(self) -> str:
        return f"{self._realm_base}/protocol/openid-connect/auth"

    @property
    def token_endpoint_fallback(self) -> str:
        return f"{self._realm_base}/protocol/openid-connect/token"
