"""OAuth2 / OpenID Connect (Keycloak) mit Authorization Code Flow + PKCE.

Basiert 1:1 auf dem simap "Quick Guide Authorisation Code Flow" (Stand Mai 2025).
2FA ist Pflicht und an einen echten User gebunden -> einmaliger interaktiver
Login im Browser, danach Selbsterhalt ueber den Refresh Token.

Ablauf:
  auth = SimapAuth(cfg)
  token = auth.get_access_token()   # oeffnet Browser falls noetig, sonst Cache/Refresh
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

import requests

from .config import SimapConfig


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _make_pkce() -> tuple[str, str]:
    """Gibt (code_verifier, code_challenge) zurueck. S256, 43-128 Zeichen."""
    verifier = _b64url(secrets.token_bytes(64))  # ~86 Zeichen
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Faengt den Redirect mit ?code=... ab."""
    auth_code: str | None = None
    state: str | None = None

    def do_GET(self) -> None:  # noqa: N802
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        _CallbackHandler.auth_code = params.get("code", [None])[0]
        _CallbackHandler.state = params.get("state", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        msg = "Login erfolgreich. Du kannst dieses Fenster schliessen."
        self.wfile.write(f"<html><body><h3>{msg}</h3></body></html>".encode())

    def log_message(self, *args) -> None:  # Stille
        pass


class SimapAuth:
    def __init__(self, config: SimapConfig | None = None) -> None:
        self.cfg = config or SimapConfig()
        self._oidc: dict | None = None
        self._token_file = Path(self.cfg.token_cache_path)

    # --- OIDC Discovery ---------------------------------------------------

    @property
    def oidc(self) -> dict:
        if self._oidc is None:
            try:
                r = requests.get(self.cfg.oidc_discovery_url, timeout=self.cfg.timeout_s)
                r.raise_for_status()
                self._oidc = r.json()
            except requests.RequestException:
                # Fallback auf die im Quick Guide dokumentierten Endpunkte
                self._oidc = {
                    "authorization_endpoint": self.cfg.auth_endpoint_fallback,
                    "token_endpoint": self.cfg.token_endpoint_fallback,
                }
        return self._oidc

    @property
    def auth_endpoint(self) -> str:
        return self.oidc["authorization_endpoint"]

    @property
    def token_endpoint(self) -> str:
        return self.oidc["token_endpoint"]

    # --- Token-Cache ------------------------------------------------------

    def _load_cache(self) -> dict | None:
        if self._token_file.exists():
            try:
                return json.loads(self._token_file.read_text())
            except json.JSONDecodeError:
                return None
        return None

    def _save_cache(self, tok: dict) -> None:
        tok = dict(tok)
        tok["_obtained_at"] = time.time()
        self._token_file.write_text(json.dumps(tok))
        os.chmod(self._token_file, 0o600)  # Token nicht weltlesbar

    # --- Hauptmethode -----------------------------------------------------

    def get_access_token(self) -> str:
        # M2M-Pfad: falls von simap freigeschaltet, kein Browser/2FA noetig
        if self.cfg.use_client_credentials:
            tok = self._load_cache()
            if tok and time.time() - tok.get("_obtained_at", 0) < tok.get("expires_in", 0) - 60:
                return tok["access_token"]
            return self._client_credentials()["access_token"]

        tok = self._load_cache()
        if tok:
            age = time.time() - tok.get("_obtained_at", 0)
            # 60s Puffer vor Ablauf
            if age < tok.get("expires_in", 0) - 60:
                return tok["access_token"]
            if tok.get("refresh_token"):
                refreshed = self._refresh(tok["refresh_token"])
                if refreshed:
                    return refreshed["access_token"]
        # Kein gueltiger Token -> interaktiver Login
        new = self._interactive_login()
        return new["access_token"]

    # --- Refresh ----------------------------------------------------------

    def _refresh(self, refresh_token: str) -> dict | None:
        data = {
            "grant_type": "refresh_token",
            "client_id": self.cfg.client_id,
            "scope": self.cfg.scope,
            "refresh_token": refresh_token,
        }
        if self.cfg.client_secret:
            data["client_secret"] = self.cfg.client_secret
        r = requests.post(self.token_endpoint, data=data, timeout=self.cfg.timeout_s)
        if r.status_code != 200:
            return None
        tok = r.json()
        self._save_cache(tok)
        return tok

    # --- Client Credentials (M2M, falls freigeschaltet) ------------------

    def _client_credentials(self) -> dict:
        if not self.cfg.client_secret:
            raise RuntimeError("Client Credentials brauchen SIMAP_CLIENT_SECRET.")
        data = {
            "grant_type": "client_credentials",
            "client_id": self.cfg.client_id,
            "client_secret": self.cfg.client_secret,
            "scope": self.cfg.scope,
        }
        r = requests.post(self.token_endpoint, data=data, timeout=self.cfg.timeout_s)
        r.raise_for_status()
        tok = r.json()
        self._save_cache(tok)
        return tok

    # --- Interaktiver Login (Code Flow + PKCE) ---------------------------

    def _interactive_login(self) -> dict:
        verifier, challenge = _make_pkce()
        state = secrets.token_urlsafe(16)

        params = {
            "response_type": "code",
            "client_id": self.cfg.client_id,
            "redirect_uri": self.cfg.redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": self.cfg.scope,
            "state": state,
        }
        url = f"{self.auth_endpoint}?{urllib.parse.urlencode(params)}"

        # Lokalen Callback-Server starten
        host, port = self._redirect_host_port()
        server = http.server.HTTPServer((host, port), _CallbackHandler)
        _CallbackHandler.auth_code = None
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()

        print("Browser wird geoeffnet fuer den simap-Login (inkl. 2FA)...")
        webbrowser.open(url)
        print(f"Falls sich nichts oeffnet, oeffne manuell:\n{url}")

        t.join(timeout=300)  # max 5 Min auf Login warten
        server.server_close()

        code = _CallbackHandler.auth_code
        if not code:
            raise RuntimeError("Kein Authorization Code erhalten (Timeout/Abbruch).")
        if _CallbackHandler.state != state:
            raise RuntimeError("State stimmt nicht ueberein (moeglicher CSRF).")

        return self._exchange_code(code, verifier)

    def _exchange_code(self, code: str, verifier: str) -> dict:
        data = {
            "grant_type": "authorization_code",
            "client_id": self.cfg.client_id,
            "redirect_uri": self.cfg.redirect_uri,
            "code": code,
            "code_verifier": verifier,
        }
        if self.cfg.client_secret:
            data["client_secret"] = self.cfg.client_secret
        r = requests.post(self.token_endpoint, data=data, timeout=self.cfg.timeout_s)
        r.raise_for_status()
        tok = r.json()
        self._save_cache(tok)
        return tok

    def _redirect_host_port(self) -> tuple[str, int]:
        parsed = urllib.parse.urlparse(self.cfg.redirect_uri)
        return parsed.hostname or "localhost", parsed.port or 8765
