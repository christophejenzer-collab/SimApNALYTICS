"""SimApNALYTICS -- Ausschreibungs-/Zuschlagsanalyse (Streamlit).

Start:
    pip install -r requirements.txt
    streamlit run dashboard.py
"""
from __future__ import annotations

import io
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from simapnalytics.api.client import SimapClient
from simapnalytics.analysis import analyzer as az
from simapnalytics.cpv_catalog import CPV_CATEGORIES, codes_for, all_codes_with_labels

CANTONS = ["AG", "AI", "AR", "BE", "BL", "BS", "FR", "GE", "GL", "GR", "JU",
           "LU", "NE", "NW", "OW", "SG", "SH", "SO", "SZ", "TG", "TI", "UR",
           "VD", "VS", "ZG", "ZH"]
SUBTYPES = {"construction": "Bau", "service": "Dienstleistung", "supply": "Lieferung"}
SIMAP_START = date(2024, 7, 1)
SIMAP_PROJECT_URL = "https://www.simap.ch/de/project-detail/{project_id}"

st.set_page_config(page_title="SimApNALYTICS", layout="wide",
                   initial_sidebar_state="expanded")


# ===== Helper: Daten holen ===============================================

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_awards(search, cantons, cpv, von, bis, subtypes, max_n) -> pd.DataFrame:
    """Lädt Zuschläge mit Detailangaben. Gecacht 1 Stunde."""
    client = SimapClient()
    awards = list(client.find_awards(
        search=search or None,
        cantons=cantons or None,
        cpv_codes=cpv or None,
        publication_from=von or None,
        publication_until=bis or None,
        project_sub_types=subtypes or None,
        lang="de",
        max_results=max_n,
    ))
    return az.to_frame(awards)


def make_simap_link(project_id) -> str | None:
    if not project_id or pd.isna(project_id):
        return None
    return SIMAP_PROJECT_URL.format(project_id=project_id)


def base_table(df: pd.DataFrame) -> pd.DataFrame:
    """Anzeigetabelle mit klickbarem Link zur Original-Ausschreibung."""
    if df.empty:
        return df
    return pd.DataFrame({
        "Titel": df["title"],
        "Kanton": df["canton"],
        "Beschaffungsstelle": df["proc_office"],
        "Zuschlagsempfänger": df["award_companies"].apply(lambda x: ", ".join(x)),
        "Zuschlagsdatum": df["award_date"].dt.date if "award_date" in df else None,
        "Summe (CHF)": df["award_price"],
        "Währung": df["award_currency"],
        "Anbieter": df["nr_of_offers"],
        "Verfahren": df["process_type"],
        "Auf simap.ch öffnen": df["project_id"].apply(make_simap_link),
    })


def show_table(df: pd.DataFrame) -> None:
    """Tabelle mit klickbaren Links."""
    st.dataframe(df, use_container_width=True, hide_index=True,
                 column_config={
                     "Auf simap.ch öffnen": st.column_config.LinkColumn(
                         display_text="↗ Öffnen"),
                     "Summe (CHF)": st.column_config.NumberColumn(
                         format="%.2f"),
                 })


def build_excel(df: pd.DataFrame, ranking: pd.DataFrame | None = None,
                trends: pd.DataFrame | None = None,
                cpv_dist: pd.DataFrame | None = None) -> bytes:
    """Mehrblättriger Excel-Export mit Original-Link als Spalte."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        out = base_table(df).copy()
        out.to_excel(xl, index=False, sheet_name="Zuschlaege")
        if ranking is not None and not ranking.empty:
            ranking.to_excel(xl, index=False, sheet_name="Rangliste")
        if trends is not None and not trends.empty:
            trends.to_excel(xl, index=False, sheet_name="Volumen_Zeit")
        if cpv_dist is not None and not cpv_dist.empty:
            cpv_dist.to_excel(xl, index=False, sheet_name="CPV_Verteilung")
    return buf.getvalue()


# ===== Session State fuer Beispielsuchen + Filterdaten ==================

if "preset" not in st.session_state:
    st.session_state.preset = None
if "df" not in st.session_state:
    st.session_state.df = pd.DataFrame()
if "last_query" not in st.session_state:
    st.session_state.last_query = None


PRESETS = {
    "🏗 Architektur Schweiz (letzte 90 Tage)": {
        "cpv_text": "71200000, 71240000",
        "cantons": [],
        "subtypes": [],
        "von": date.today() - timedelta(days=90),
        "bis": date.today(),
        "max_n": 200,
    },
    "🛣 Strassenbau Kanton Bern (2025-2026)": {
        "cpv_text": "45233000, 45233140",
        "cantons": ["BE"],
        "subtypes": ["construction"],
        "von": date(2025, 1, 1),
        "bis": date.today(),
        "max_n": 200,
    },
    "💻 IT-Zuschläge schweizweit (seit simap-Start)": {
        "cpv_text": "72000000, 48000000",
        "cantons": [],
        "subtypes": ["service"],
        "von": SIMAP_START,
        "bis": date.today(),
        "max_n": 300,
    },
    "🖨 Drucken / Kopieren (Marktübersicht)": {
        "cpv_text": "30120000, 30232100, 79800000, 50313000",
        "cantons": [],
        "subtypes": [],
        "von": SIMAP_START,
        "bis": date.today(),
        "max_n": 200,
    },
}


def apply_preset(name: str) -> None:
    p = PRESETS[name]
    st.session_state.preset = p
    # In Widget-Keys schreiben (werden im Sidebar als Defaults gelesen)
    for k, v in p.items():
        st.session_state[f"sb_{k}"] = v


# ===== Header ============================================================

st.title("SimApNALYTICS")
st.caption("Ausschreibungs- und Zuschlagsanalyse  ·  öffentliche simap-API  ·  kein Login")


# ===== Sidebar (alle Filter) ============================================

with st.sidebar:
    st.header("Filter")

    # CPV-Auswahl: Kategorie + Feinauswahl + Freitext
    with st.expander("CPV-Codes wählen", expanded=True):
        cat_options = ["– keine Kategorie –"] + list(CPV_CATEGORIES.keys())
        sel_cat = st.selectbox("Kategorie", cat_options, index=0,
                               key="sb_cat",
                               help="Schnellauswahl einer Domain (z.B. Architektur).")
        cat_codes = codes_for(sel_cat) if sel_cat != "– keine Kategorie –" else []
        if cat_codes:
            items = [(c, lbl) for cat, c, lbl in all_codes_with_labels()
                     if cat == sel_cat]
            labels = {c: f"{c} – {lbl}" for c, lbl in items}
            sel_codes = st.multiselect(
                "Codes der Kategorie (leer = alle)",
                options=[c for c, _ in items],
                default=[],
                format_func=lambda c: labels[c],
                key="sb_subset",
            )
            cat_codes = sel_codes or cat_codes
        cpv_text = st.text_input("Zusätzliche Codes (Komma)",
                                 key="sb_cpv_text",
                                 placeholder="z.B. 45211000")
        extra = [c.strip() for c in cpv_text.split(",") if c.strip()]
        cpv_active = list(dict.fromkeys(cat_codes + extra))
        if cpv_active:
            st.caption(f"Aktiv: {', '.join(cpv_active)}")

    # Sonstige Filter
    sb_search = st.text_input("Suchtext (≥3 Zeichen)", key="sb_search",
                              placeholder="z.B. Sanierung")
    sb_cantons = st.multiselect("Kantone", CANTONS, key="sb_cantons")
    sb_subtypes = st.multiselect("Projekttyp", list(SUBTYPES),
                                  format_func=lambda k: SUBTYPES[k],
                                  key="sb_subtypes")
    today = date.today()
    sb_von = st.date_input("Publikation ab", value=today - timedelta(days=30),
                            min_value=SIMAP_START, max_value=today, key="sb_von")
    sb_bis = st.date_input("Publikation bis", value=today,
                            min_value=SIMAP_START, max_value=today, key="sb_bis")
    sb_max = st.slider("Max. Treffer", 20, 1000, 100, step=20, key="sb_max_n")

    go = st.button("🔍 Suchen", type="primary", use_container_width=True)
    if st.button("↺ Filter zurücksetzen", use_container_width=True):
        for k in list(st.session_state.keys()):
            if k.startswith("sb_"):
                del st.session_state[k]
        st.session_state.df = pd.DataFrame()
        st.rerun()

    st.divider()
    st.caption(f"Daten ab {SIMAP_START.isoformat()} (simap-Start) bis heute. "
               "Pro Zuschlag werden Details nachgeladen — grössere Mengen "
               "dauern entsprechend länger.")


# ===== Suche auslösen ====================================================

if go:
    if sb_von > sb_bis:
        st.error("'Publikation ab' liegt nach 'Publikation bis' — bitte korrigieren.")
        st.stop()
    with st.spinner(f"Lade Zuschläge (bis zu {sb_max} Treffer mit Details)…"):
        try:
            st.session_state.df = fetch_awards(
                sb_search, sb_cantons, cpv_active,
                sb_von.isoformat(), sb_bis.isoformat(), sb_subtypes, sb_max)
            st.session_state.last_query = {
                "Suche": sb_search or "-", "CPV": ", ".join(cpv_active) or "-",
                "Kantone": ", ".join(sb_cantons) or "alle",
                "Zeitraum": f"{sb_von} bis {sb_bis}",
            }
        except Exception as e:  # noqa: BLE001
            st.error(f"Fehler beim Abruf: {e}")
            st.session_state.df = pd.DataFrame()

df = st.session_state.df


# ===== Tabs ==============================================================

tab_home, tab_res, tab_win, tab_trend, tab_market = st.tabs(
    ["🏠 Start", "📋 Resultate", "🏆 Wer gewinnt", "📈 Trends", "📊 Marktanalyse"]
)


# ----- Tab Start (Welcome + Beispielsuchen) -----------------------------

with tab_home:
    st.subheader("Willkommen")
    st.markdown(
        "**SimApNALYTICS** liest öffentlich publizierte Zuschläge von "
        "simap.ch und macht sie auswertbar:\n\n"
        "- **Resultate** — alle gefundenen Zuschläge mit Empfänger, Datum, Summe, "
        "Link zur Original-Publikation\n"
        "- **Wer gewinnt** — Ranking der erfolgreichen Firmen plus Wettbewerbsdichte\n"
        "- **Trends** — Volumen über Zeit, CPV-Verteilung\n"
        "- **Marktanalyse** — Marktanteile und Rangliste für eine ganze CPV-Domain"
    )
    st.markdown("##### Schnellstart – Klick auf eine Beispielsuche")
    cols = st.columns(2)
    for i, name in enumerate(PRESETS):
        with cols[i % 2]:
            if st.button(name, use_container_width=True, key=f"preset_{i}"):
                apply_preset(name)
                st.toast(f"Filter gesetzt: {name}. Klicke jetzt links auf **Suchen**.")
                st.rerun()
    st.divider()
    st.caption("Oder stelle die Filter links manuell ein und klicke **Suchen**.")


# ----- Tab Resultate ----------------------------------------------------

with tab_res:
    if df.empty:
        st.info("Stelle links die Filter ein und klicke **Suchen** – oder nutze "
                "eine Beispielsuche auf der Start-Seite.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Treffer", len(df))
        c2.metric("Total CHF", f"{df['award_price'].sum(skipna=True):,.0f}")
        c3.metric("Mit Preis",
                  f"{df['award_price'].notna().sum()}/{len(df)}")

        if st.session_state.last_query:
            with st.expander("Aktive Filter"):
                for k, v in st.session_state.last_query.items():
                    st.write(f"**{k}:** {v}")

        show_table(base_table(df))

        # Tab-Export
        csv = base_table(df).to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇ CSV (Resultate)", csv,
                           "simapnalytics_resultate.csv", "text/csv")


# ----- Tab Wer gewinnt --------------------------------------------------

if not df.empty:
    ranking = az.winners_ranking(df, top=25)
    if not ranking.empty and "Summe_CHF" in ranking:
        total_all = df["award_price"].sum(skipna=True)
        if total_all > 0:
            ranking = ranking.copy()
            ranking.insert(1, "Rang", range(1, len(ranking) + 1))
            ranking["Marktanteil %"] = (ranking["Summe_CHF"] / total_all * 100).round(2)
else:
    ranking = pd.DataFrame()

with tab_win:
    if df.empty:
        st.caption("Bitte erst suchen.")
    elif ranking.empty:
        st.warning("Keine Zuschläge mit Preis und Empfänger für Ranking.")
    else:
        st.subheader("Ranking der Zuschlagsempfänger")
        st.dataframe(ranking, use_container_width=True, hide_index=True)
        st.bar_chart(ranking.set_index("Firma")["Summe_CHF"].head(15))

        st.subheader("Wettbewerbsdichte je Kanton")
        st.caption("Ø Anzahl Anbieter pro Zuschlag – tief = wenig Konkurrenz.")
        st.dataframe(az.competition_density(df), use_container_width=True, hide_index=True)

        # Tab-Export: Ranking
        csv = ranking.to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇ CSV (Rangliste)", csv,
                           "simapnalytics_rangliste.csv", "text/csv")


# ----- Tab Trends -------------------------------------------------------

vol = az.volume_over_time(df, freq="ME") if not df.empty else pd.DataFrame()
cpv_dist = az.cpv_distribution(df, level=2, top=15) if not df.empty else pd.DataFrame()

with tab_trend:
    if df.empty:
        st.caption("Bitte erst suchen.")
    else:
        st.subheader("Volumen über Zeit (nach Zuschlagsdatum)")
        if not vol.empty:
            st.line_chart(vol.set_index("Periode")["Anzahl"])
        st.subheader("Häufigste CPV-Gruppen")
        st.dataframe(cpv_dist, use_container_width=True, hide_index=True)


# ----- Tab Marktanalyse -------------------------------------------------

with tab_market:
    if df.empty:
        st.info("Die Marktanalyse nutzt deine aktuelle Suche. Bitte links "
                "Filter einstellen und **Suchen** klicken.")
    else:
        total = df["award_price"].sum(skipna=True)
        n_total = len(df)
        n_with_price = int(df["award_price"].notna().sum())
        firms = df.explode("award_companies")["award_companies"]
        firms = firms[firms.notna() & (firms != "")]
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Zuschläge", n_total)
        k2.metric("Marktvolumen (CHF)", f"{total:,.0f}")
        k3.metric("Anbieter (unique)", firms.nunique())
        k4.metric("Mit Preis", f"{n_with_price}/{n_total}")
        if n_with_price < n_total:
            st.caption(f"{n_total - n_with_price} Zuschläge ohne publizierte "
                       "Summe fliessen in Anzahlen, nicht ins Marktvolumen.")

        if not ranking.empty:
            st.subheader("Rangliste der Marktanteile")
            st.dataframe(ranking[["Rang", "Firma", "Zuschlaege",
                                  "Summe_CHF", "Marktanteil %"]],
                         use_container_width=True, hide_index=True)
            st.bar_chart(ranking.set_index("Firma")["Summe_CHF"].head(15))

        st.subheader("Aufträge je Firma")
        st.caption("Pro Firma alle gewonnenen Aufträge.")
        for firma in (ranking["Firma"].tolist() if not ranking.empty else []):
            rows = df[df["award_companies"].apply(lambda x: firma in (x or []))]
            if rows.empty:
                continue
            summe = rows["award_price"].sum(skipna=True)
            with st.expander(
                f"{firma}  ·  {len(rows)} Auftrag/Aufträge  ·  CHF {summe:,.2f}"
            ):
                tbl = pd.DataFrame({
                    "Datum": rows["award_date"].dt.date,
                    "Titel": rows["title"],
                    "Stelle": rows["proc_office"],
                    "Kanton": rows["canton"],
                    "Summe (CHF)": rows["award_price"],
                    "Anbieter": rows["nr_of_offers"],
                    "Verfahren": rows["process_type"],
                    "Auf simap.ch öffnen": rows["project_id"].apply(make_simap_link),
                }).sort_values("Datum", ascending=False)
                st.dataframe(tbl, use_container_width=True, hide_index=True,
                             column_config={
                                 "Auf simap.ch öffnen": st.column_config.LinkColumn(
                                     display_text="↗ Öffnen"),
                                 "Summe (CHF)": st.column_config.NumberColumn(
                                     format="%.2f"),
                             })

        st.subheader("Marktvolumen über Zeit")
        ts = df.dropna(subset=["award_date"]).copy()
        if not ts.empty:
            ts["Periode"] = ts["award_date"].dt.to_period("Q").dt.to_timestamp()
            agg = ts.groupby("Periode").agg(
                Anzahl=("award_date", "size"),
                Summe_CHF=("award_price", "sum"),
            ).reset_index()
            c_left, c_right = st.columns(2)
            c_left.caption("Anzahl Zuschläge pro Quartal")
            c_left.bar_chart(agg.set_index("Periode")["Anzahl"])
            c_right.caption("Marktvolumen pro Quartal (CHF)")
            c_right.bar_chart(agg.set_index("Periode")["Summe_CHF"])


# ===== Globaler Export (alles als Excel, am Ende der Seite) ============

if not df.empty:
    st.divider()
    st.subheader("Export")
    excel_bytes = build_excel(df, ranking=ranking,
                              trends=vol if not vol.empty else None,
                              cpv_dist=cpv_dist if not cpv_dist.empty else None)
    st.download_button(
        "⬇ Alles als Excel (Zuschläge, Rangliste, Volumen, CPV)",
        excel_bytes,
        "simapnalytics_gesamtexport.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True,
    )
    st.caption("Enthält alle Daten der aktuellen Suche in mehreren "
               "Tabellenblättern, inklusive Link zur Original-Publikation.")
