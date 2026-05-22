"""Analyse-Funktionen auf einer Liste von Award-Objekten (SimApNALYTICS).

Passend zum v2-Award-Modell. Drei Bereiche:
1. Markt/Wettbewerb  -> Ranking Zuschlagsempfaenger, Wettbewerbsdichte
2. Filter            -> nach Firma, Kanton, CPV
3. Statistik/Trends  -> Volumen ueber Zeit, CPV-Verteilung
"""
from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from ..models import Award


def to_frame(awards: Iterable[Award]) -> pd.DataFrame:
    df = pd.DataFrame(a.to_dict() for a in awards)
    if df.empty:
        return df
    for col in ("award_date", "project_start", "project_end", "publication_date"):
        if col in df:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


# --- 1. Markt / Wettbewerb -----------------------------------------------

def winners_ranking(df: pd.DataFrame, top: int = 20) -> pd.DataFrame:
    """Ranking der Zuschlagsempfaenger nach Anzahl Zuschlaegen und Gesamtsumme."""
    if df.empty or "award_companies" not in df:
        return pd.DataFrame(columns=["Firma", "Zuschlaege", "Summe_CHF"])
    ex = df.explode("award_companies")
    ex = ex[ex["award_companies"].notna() & (ex["award_companies"] != "")]
    if ex.empty:
        return pd.DataFrame(columns=["Firma", "Zuschlaege", "Summe_CHF"])
    g = ex.groupby("award_companies").agg(
        Zuschlaege=("award_companies", "size"),
        Summe_CHF=("award_price", "sum"),
    )
    g = g.sort_values(["Summe_CHF", "Zuschlaege"], ascending=False).head(top)
    return g.reset_index().rename(columns={"award_companies": "Firma"})


def competition_density(df: pd.DataFrame) -> pd.DataFrame:
    """Durchschnittliche Anbieterzahl pro Kanton (Wettbewerbsdruck)."""
    if df.empty or "nr_of_offers" not in df:
        return pd.DataFrame(columns=["Kanton", "Anbieter_Schnitt", "Anzahl"])
    d = df[df["nr_of_offers"].notna()]
    if d.empty:
        return pd.DataFrame(columns=["Kanton", "Anbieter_Schnitt", "Anzahl"])
    g = d.groupby("canton").agg(
        Anbieter_Schnitt=("nr_of_offers", "mean"),
        Anzahl=("nr_of_offers", "size"),
    )
    return g.sort_values("Anbieter_Schnitt").reset_index().rename(columns={"canton": "Kanton"})


# --- 2. Filter ------------------------------------------------------------

def filter_awards(df: pd.DataFrame, *, company_contains: str | None = None,
                  cantons: list[str] | None = None,
                  cpv_prefixes: list[str] | None = None) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if cantons:
        out = out[out["canton"].isin(cantons)]
    if cpv_prefixes:
        out = out[out["cpv"].apply(
            lambda codes: any(str(c).startswith(p) for c in (codes or []) for p in cpv_prefixes))]
    if company_contains:
        s = company_contains.lower()
        out = out[out["award_companies"].apply(
            lambda lst: any(s in str(c).lower() for c in (lst or [])))]
    return out


# --- 3. Statistik / Trends ------------------------------------------------

def volume_over_time(df: pd.DataFrame, freq: str = "ME") -> pd.DataFrame:
    """Anzahl Zuschlaege je Periode (nach Zuschlagsdatum)."""
    if df.empty or "award_date" not in df:
        return pd.DataFrame(columns=["Periode", "Anzahl"])
    s = df.dropna(subset=["award_date"]).set_index("award_date").resample(freq).size()
    out = s.rename("Anzahl").reset_index()
    return out.rename(columns={out.columns[0]: "Periode"})


def cpv_distribution(df: pd.DataFrame, level: int = 2, top: int = 15) -> pd.DataFrame:
    """Haeufigste CPV-Gruppen (level = Anzahl fuehrender Ziffern)."""
    if df.empty or "cpv" not in df:
        return pd.DataFrame(columns=["CPV_Gruppe", "Anzahl"])
    rows = df.explode("cpv")
    rows = rows[rows["cpv"].notna() & (rows["cpv"] != "")]
    if rows.empty:
        return pd.DataFrame(columns=["CPV_Gruppe", "Anzahl"])
    rows = rows.assign(CPV_Gruppe=rows["cpv"].astype(str).str[:level])
    g = rows.groupby("CPV_Gruppe").size().rename("Anzahl")
    return g.sort_values(ascending=False).head(top).reset_index()
