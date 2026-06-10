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
        "Laufzeit (Mt.)": df.get("duration_main_months"),
        "Vertragsende (geschätzt)": pd.to_datetime(
            df.get("duration_end_estimated"), errors="coerce").dt.date
            if "duration_end_estimated" in df else None,
        "Confidence": df.get("duration_confidence"),
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
    "🏗 Architektur Schweiz (seit simap-Start)": {
        "cpv_text": "71200000, 71240000",
        "cantons": [],
        "subtypes": [],
        "von": SIMAP_START,
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
    sb_von = st.date_input("Publikation ab", value=SIMAP_START,
                            min_value=SIMAP_START, max_value=today, key="sb_von",
                            help="Frühestes Datum: 01.07.2024 (simap-Start). "
                                 "Stelle hier den gewünschten Beginn des "
                                 "Rückblicks ein.")
    sb_bis = st.date_input("Publikation bis", value=today,
                            min_value=SIMAP_START, max_value=today, key="sb_bis")
    sb_max = st.slider("Max. Treffer", 20, 1000, 100, step=20, key="sb_max_n")

    go = st.button("🔍 Suchen", type="primary", use_container_width=True)
    if st.button("↺ Filter zurücksetzen", use_container_width=True):
        for k in list(st.session_state.keys()):
            if k.startswith("sb_"):
                del st.session_state[k]
        st.session_state.df = pd.DataFrame()
        st.session_state.search_performed = False
        st.session_state.last_query = None
        st.rerun()

    st.divider()
    st.caption(f"Daten ab {SIMAP_START.isoformat()} (simap-Start) bis heute. "
               "Pro Zuschlag werden Details nachgeladen — grössere Mengen "
               "dauern entsprechend länger.")


# ===== Suche auslösen ====================================================

if "search_performed" not in st.session_state:
    st.session_state.search_performed = False

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
            st.session_state.search_performed = True
        except Exception as e:  # noqa: BLE001
            st.error(f"Fehler beim Abruf: {e}")
            st.session_state.df = pd.DataFrame()

df = st.session_state.df


# ===== Tabs ==============================================================

# Tabs dynamisch: Start verschwindet nach erster Suche (auch wenn leer),
# Resultate rueckt vorn und ist automatisch aktiv.
if st.session_state.search_performed:
    tab_res, tab_win, tab_trend, tab_market, tab_renew, tab_tender, tab_partners = st.tabs(
        ["📋 Resultate", "🏆 Wer gewinnt", "📈 Trends",
         "📊 Marktanalyse", "🔁 Wiedervergabe", "📢 Offene Ausschreibungen",
         "🤝 Anbieter & Vergeber"]
    )
    tab_home = None
else:
    tab_home, tab_res, tab_win, tab_trend, tab_market, tab_renew, tab_tender, tab_partners = st.tabs(
        ["🏠 Start", "📋 Resultate", "🏆 Wer gewinnt", "📈 Trends",
         "📊 Marktanalyse", "🔁 Wiedervergabe", "📢 Offene Ausschreibungen",
         "🤝 Anbieter & Vergeber"]
    )


# ----- Tab Start (Welcome + Beispielsuchen) -----------------------------
# Nur wenn noch keine Suche gemacht wurde, ist tab_home vorhanden.

if tab_home is not None:
    with tab_home:
        st.subheader("Willkommen")
        st.markdown(
            "**SimApNALYTICS** liest öffentlich publizierte Zuschläge von "
            "simap.ch und macht sie auswertbar:\n\n"
            "- **Resultate** — alle gefundenen Zuschläge mit Empfänger, Datum, Summe, "
            "Link zur Original-Publikation\n"
            "- **Wer gewinnt** — Ranking der erfolgreichen Firmen plus Wettbewerbsdichte\n"
            "- **Trends** — Volumen über Zeit, CPV-Verteilung\n"
            "- **Marktanalyse** — Marktanteile und Rangliste für eine ganze CPV-Domain\n"
            "- **Wiedervergabe** — anstehende Vertragsenden (heuristisch geschätzt)"
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


# ----- Tab Wiedervergabe ------------------------------------------------

with tab_renew:
    st.subheader("Wiedervergabe-Radar")
    st.markdown(
        "Zeigt Aufträge der aktuellen Suche, deren **geschätztes Vertragsende** "
        "in einem wählbaren Zukunftsfenster liegt — also Aufträge, die "
        "voraussichtlich bald neu ausgeschrieben werden."
    )
    st.warning(
        "**Wichtig — Schätzung, nicht Garantie.** simap stellt keine "
        "strukturierten Laufzeitfelder bereit. Die Laufzeit wird heuristisch "
        "aus dem Beschreibungstext geparst (z. B. *Laufzeit 5 Jahre*). "
        "Treffer haben eine Confidence (high/medium/low). Aufträge ohne "
        "erkennbare Laufzeit (Bauarbeiten, einmalige Lieferungen) erscheinen "
        "**nicht** in dieser Liste."
    )

    if df.empty:
        st.info("Bitte erst links Filter setzen und **Suchen** klicken.")
    elif "duration_end_estimated" not in df.columns:
        st.warning("Keine Vertragslaufzeit-Daten verfügbar – ggf. Daten neu laden.")
    else:
        # Filter
        f_col1, f_col2, f_col3 = st.columns([1, 1, 1])
        horizon_months = f_col1.slider(
            "Vorausschau (Monate ab heute)", 6, 60, 24, step=6,
            help="Welche Vertragsenden im nächsten Zeitraum interessieren dich?",
            key="renew_horizon",
        )
        include_max = f_col2.checkbox(
            "Auch Optionen ausgeschöpft betrachten",
            value=False,
            help="Statt regulärem Ende das Maximum (mit allen Optionen) nutzen.",
            key="renew_max",
        )
        min_conf = f_col3.selectbox(
            "Mindest-Confidence", ["high", "medium", "low"], index=1,
            help="Filtert unsichere Schätzungen heraus.",
            key="renew_conf",
        )

        # Confidence-Hierarchie
        conf_rank = {"high": 3, "medium": 2, "low": 1, "none": 0}
        threshold = conf_rank[min_conf]

        # Datenbasis: nur Awards mit Vertragsende-Schätzung
        end_col = "duration_end_max_estimated" if include_max \
            else "duration_end_estimated"
        renew_df = df[df[end_col].notna() &
                      df["duration_confidence"].map(conf_rank).ge(threshold)].copy()
        if renew_df.empty:
            st.info("Keine Aufträge mit Laufzeit-Schätzung in der aktuellen "
                    "Suche. Versuche eine andere Domain (z. B. IT, MPS, "
                    "Wartung) — bei Bauaufträgen gibt es typischerweise keine "
                    "Laufzeit-Angabe.")
        else:
            renew_df["_end"] = pd.to_datetime(renew_df[end_col], errors="coerce")
            today = pd.Timestamp(date.today())
            horizon_end = today + pd.DateOffset(months=horizon_months)
            in_window = renew_df[
                (renew_df["_end"] >= today) & (renew_df["_end"] <= horizon_end)
            ].sort_values("_end")

            c1, c2, c3 = st.columns(3)
            c1.metric("Mit Laufzeit", len(renew_df))
            c2.metric(f"Ablauf in {horizon_months} Mt.", len(in_window))
            c3.metric("Total CHF (Fenster)",
                      f"{in_window['award_price'].sum(skipna=True):,.0f}")

            if in_window.empty:
                st.success("Keine Verträge in diesem Fenster auslaufend.")
            else:
                st.subheader("Anstehende Wiedervergaben")
                tbl = pd.DataFrame({
                    "Vertragsende (geschätzt)": in_window["_end"].dt.date,
                    "Titel": in_window["title"],
                    "Aktueller Empfänger": in_window["award_companies"].apply(
                        lambda x: ", ".join(x)),
                    "Stelle": in_window["proc_office"],
                    "Kanton": in_window["canton"],
                    "Original-Summe (CHF)": in_window["award_price"],
                    "Laufzeit (Mt.)": in_window["duration_main_months"],
                    "Confidence": in_window["duration_confidence"],
                    "Auf simap.ch öffnen": in_window["project_id"].apply(make_simap_link),
                })
                st.dataframe(tbl, use_container_width=True, hide_index=True,
                             column_config={
                                 "Auf simap.ch öffnen": st.column_config.LinkColumn(
                                     display_text="↗ Öffnen"),
                                 "Original-Summe (CHF)": st.column_config.NumberColumn(
                                     format="%.2f"),
                             })

                with st.expander("Wie wurde die Laufzeit erkannt?"):
                    detail = in_window[["title", "duration_source",
                                        "duration_confidence",
                                        "duration_main_months",
                                        "duration_optional_months"]].copy()
                    detail.columns = ["Titel", "Erkannte Phrasen", "Confidence",
                                      "Haupt (Mt.)", "Optionen (Mt.)"]
                    detail["Erkannte Phrasen"] = detail["Erkannte Phrasen"].apply(
                        lambda lst: " · ".join(lst) if isinstance(lst, list) else "")
                    st.dataframe(detail, use_container_width=True, hide_index=True)

                csv = tbl.to_csv(index=False).encode("utf-8-sig")
                st.download_button("⬇ CSV (Wiedervergabe)", csv,
                                   "simapnalytics_wiedervergabe.csv", "text/csv")


# ----- Tab Offene Ausschreibungen --------------------------------------

with tab_tender:
    st.subheader("Offene Ausschreibungen (Tender)")
    st.markdown(
        "Suche nach **publizierten Ausschreibungen** (nicht Zuschlägen) — "
        "ersetzt das simap-E-Mail-Abo. Filter sind eigenständig, "
        "unabhängig von der Sidebar."
    )

    t1, t2 = st.columns([2, 1])
    t_cat = t1.selectbox(
        "CPV-Kategorie",
        ["– keine Kategorie –"] + list(CPV_CATEGORIES.keys()),
        index=1, key="t_cat",
        help="Schnellauswahl. Ergänzende Codes weiter unten möglich.",
    )
    t_mode = t2.radio(
        "Anzeigen", ["Nur offene", "Letzte X Tage"], index=0, key="t_mode",
        help="*Nur offene* = Eingabefrist liegt noch in der Zukunft. "
             "*Letzte X Tage* = alle Ausschreibungen seit X Tagen.",
    )

    t_cat_codes = codes_for(t_cat) if t_cat != "– keine Kategorie –" else []
    t_extra = st.text_input(
        "Zusätzliche CPV-Codes (Komma)", key="t_extra",
        placeholder="z.B. 45211000",
    )
    t_extra_codes = [c.strip() for c in t_extra.split(",") if c.strip()]
    t_cpvs = list(dict.fromkeys(t_cat_codes + t_extra_codes))

    t3, t4, t5 = st.columns(3)
    t_cantons = t3.multiselect("Kantone", CANTONS, key="t_cantons")
    if t_mode == "Letzte X Tage":
        t_days = t4.slider("Tage zurück", 7, 180, 30, step=7, key="t_days")
        t_only_open = False
    else:
        t_days = 90
        t4.caption("Suche umfasst Publikationen der letzten 90 Tage.")
        t_only_open = True
    t_max = t5.number_input(
        "Max. Treffer", min_value=20, max_value=500, value=100, step=20,
        key="t_max",
    )

    if t_cpvs:
        st.caption(f"Aktive CPV-Codes: **{', '.join(t_cpvs)}**")
    t_go = st.button(
        "🔍 Ausschreibungen suchen", type="primary",
        use_container_width=True, key="t_go",
        disabled=not t_cpvs,
    )

    if not t_cpvs:
        st.info("Wähle oben eine CPV-Kategorie oder gib eigene Codes ein.")
    elif not t_go and "t_df" not in st.session_state:
        st.info("Klicke **Ausschreibungen suchen**.")
    else:
        if t_go:
            from_date = (date.today() - timedelta(days=t_days)).isoformat()
            try:
                with st.spinner("Lade Ausschreibungen mit Details…"):
                    client = SimapClient()
                    tenders = list(client.find_tenders(
                        cpv_codes=t_cpvs,
                        cantons=t_cantons or None,
                        publication_from=from_date,
                        only_open=t_only_open,
                        lang="de",
                        max_results=int(t_max),
                    ))
                rows = [t.to_dict() for t in tenders]
                t_df = pd.DataFrame(rows)
                for col in ("offer_deadline", "publication_date",
                            "initial_publication_date",
                            "documents_available_until",
                            "select_participants_date",
                            "offer_validity_until",
                            "contract_start", "contract_end"):
                    if col in t_df.columns:
                        t_df[col] = pd.to_datetime(t_df[col], errors="coerce", utc=True)
                st.session_state.t_df = t_df
            except Exception as e:  # noqa: BLE001
                st.error(f"Fehler beim Abruf: {e}")
                st.session_state.t_df = pd.DataFrame()

        t_df = st.session_state.get("t_df", pd.DataFrame())
        if t_df.empty:
            st.warning("Keine Ausschreibungen zu diesen Filtern gefunden.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Treffer", len(t_df))
            with_dl = int(t_df["offer_deadline"].notna().sum()) \
                if "offer_deadline" in t_df else 0
            c2.metric("Mit Eingabefrist", with_dl)
            with_period = int((t_df["contract_source"] == "structured").sum()) \
                if "contract_source" in t_df else 0
            c3.metric("Mit Vertragslaufzeit", with_period)
            unique_cantons = int(t_df["canton"].nunique()) \
                if "canton" in t_df else 0
            c4.metric("Kantone", unique_cantons)

            t_sort = st.radio(
                "Sortieren nach",
                ["Eingabefrist (aufsteigend)",
                 "Publikationsdatum (neueste zuerst)"],
                index=0, horizontal=True, key="t_sort",
            )
            if t_sort.startswith("Eingabefrist"):
                t_df = t_df.sort_values("offer_deadline", na_position="last")
            else:
                t_df = t_df.sort_values("publication_date", ascending=False,
                                         na_position="last")

            tbl = pd.DataFrame({
                "Eingabefrist": t_df["offer_deadline"].dt.date
                    if "offer_deadline" in t_df else None,
                "Publikation": t_df["publication_date"].dt.date
                    if "publication_date" in t_df else None,
                "Titel": t_df["title"],
                "Kanton": t_df["canton"],
                "Stelle": t_df["proc_office"],
                "Verfahren": t_df["process_type"],
                "Vertragsbeginn": t_df["contract_start"].dt.date
                    if "contract_start" in t_df else None,
                "Vertragsende": t_df["contract_end"].dt.date
                    if "contract_end" in t_df else None,
                "Verlängerbar": t_df.get("can_be_extended"),
                "Auf simap.ch öffnen": t_df["project_id"].apply(make_simap_link),
            })
            st.dataframe(
                tbl, use_container_width=True, hide_index=True,
                column_config={
                    "Auf simap.ch öffnen": st.column_config.LinkColumn(
                        display_text="↗ Öffnen"),
                },
            )

            csv = tbl.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "⬇ CSV (Offene Ausschreibungen)", csv,
                "simapnalytics_tender.csv", "text/csv",
            )


# ----- Tab Anbieter & Vergeber ------------------------------------------

with tab_partners:
    st.subheader("Anbieter & Vergeber")
    st.markdown(
        "Suche nach Zuschlägen gefiltert über **Empfänger** (Firma, die "
        "gewonnen hat), **Vergeber** (Beschaffungsstelle) oder beidem. "
        "Bei kombinierter Suche: Wer hat von wem wann was bekommen.\n\n"
        "Diese Suche ist eigenständig — sie nutzt nicht die Sidebar-Filter."
    )

    p1, p2 = st.columns(2)
    p_company = p1.text_input(
        "Empfänger enthält…",
        placeholder="z.B. Ricoh",
        key="p_company",
        help="Teilstring im Firmennamen, case-insensitiv.",
    )
    p_office = p2.text_input(
        "Vergeber (Beschaffungsstelle) enthält…",
        placeholder="z.B. Bundesamt für Bauten",
        key="p_office",
        help="Teilstring im Namen der Beschaffungsstelle.",
    )

    # CPV-Vorfilter (Pflicht, wenn nur Empfaenger gesucht wird)
    st.markdown("**CPV-Vorfilter** (verkürzt Suche drastisch)")
    pc1, pc2 = st.columns([2, 3])
    p_cat = pc1.selectbox(
        "Kategorie",
        ["– keine Kategorie –"] + list(CPV_CATEGORIES.keys()),
        index=0, key="p_cat",
        help="simap kann nicht nach Empfängernamen filtern. Mit CPV-Vorfilter "
             "lädt das Tool nur Zuschläge dieser Domain — Faktor 20-50 "
             "schneller bei Empfänger-Suche.",
    )
    p_cat_codes = codes_for(p_cat) if p_cat != "– keine Kategorie –" else []
    p_extra = pc2.text_input(
        "Zusätzliche CPV-Codes (Komma)", key="p_extra",
        placeholder="z.B. 30232100, 30120000",
    )
    p_extra_codes = [c.strip() for c in p_extra.split(",") if c.strip()]
    p_cpvs = list(dict.fromkeys(p_cat_codes + p_extra_codes))

    p3, p4, p5 = st.columns([1, 1, 1])
    p_von = p3.date_input("Publikation ab", value=SIMAP_START,
                          min_value=SIMAP_START, max_value=today, key="p_von")
    p_bis = p4.date_input("Publikation bis", value=today,
                          min_value=SIMAP_START, max_value=today, key="p_bis")
    p_scan = p5.number_input(
        "Scan-Limit",
        min_value=200, max_value=5000, value=1000, step=200,
        key="p_scan",
        help="Max. zu durchsuchende Zuschläge. Höher = vollständiger, langsamer.",
    )

    if p_cpvs:
        st.caption(f"Aktive CPV-Codes: **{', '.join(p_cpvs)}**")

    has_company = bool(p_company.strip())
    has_office = bool(p_office.strip())
    has_input = has_company or has_office
    # CPV nötig wenn nur Empfänger gesetzt ist (sonst extrem langsam)
    needs_cpv = has_company and not has_office
    cpv_ok = bool(p_cpvs) or not needs_cpv

    if needs_cpv and not p_cpvs:
        st.warning(
            "**CPV-Vorfilter erforderlich** wenn nur ein Empfänger gesucht wird. "
            "simap kann nicht serverseitig nach Empfänger filtern — ohne CPV "
            "müsste das Tool jeden einzelnen Zuschlag im Zeitraum prüfen "
            "(Stunden). Wähle eine CPV-Kategorie oder gib Codes ein."
        )

    p_go = st.button(
        "🔍 Suchen", type="primary", use_container_width=True,
        key="p_go", disabled=not (has_input and cpv_ok),
    )

    if not has_input:
        st.info("Gib mindestens einen Empfänger ODER Vergeber ein.")
    else:
        if p_go:
            if p_von > p_bis:
                st.error("'Publikation ab' liegt nach 'Publikation bis'.")
                st.stop()

            # Fortschrittsanzeige
            progress_bar = st.progress(0.0, text="Initialisiere…")
            status_text = st.empty()

            def update_progress(scanned: int, hits: int) -> None:
                pct = min(scanned / int(p_scan), 1.0)
                progress_bar.progress(
                    pct, text=f"{scanned} von {p_scan} gescannt · {hits} Treffer"
                )

            try:
                client = SimapClient()
                awards = list(client.find_awards_filtered(
                    company_terms=[p_company.strip()] if has_company else None,
                    office_terms=[p_office.strip()] if has_office else None,
                    cpv_codes=p_cpvs or None,
                    publication_from=p_von.isoformat(),
                    publication_until=p_bis.isoformat(),
                    lang="de",
                    scan_limit=int(p_scan),
                    progress_callback=update_progress,
                ))
                progress_bar.empty()
                status_text.success(f"Fertig: {len(awards)} Treffer.")
                st.session_state.p_df = az.to_frame(awards)
            except Exception as e:  # noqa: BLE001
                progress_bar.empty()
                st.error(f"Fehler beim Abruf: {e}")
                st.session_state.p_df = pd.DataFrame()

        p_df = st.session_state.get("p_df", pd.DataFrame())
        if p_df.empty:
            if p_go:
                st.warning(
                    "Keine Treffer. Mögliche Gründe: kein Zuschlag mit diesen "
                    "Filtern im Zeitraum, Scan-Limit zu tief, oder Schreibweise "
                    "des Namens weicht ab (probier kürzeren Teilstring)."
                )
        else:
            # KPIs
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Zuschläge", len(p_df))
            c2.metric("Total CHF",
                      f"{p_df['award_price'].sum(skipna=True):,.0f}")
            offices = p_df["proc_office"].nunique() if "proc_office" in p_df else 0
            c3.metric("Vergeber (unique)", int(offices))
            firms = p_df.explode("award_companies")["award_companies"]
            firms = firms[firms.notna() & (firms != "")]
            c4.metric("Empfänger (unique)", firms.nunique())

            # Tabelle
            st.subheader("Aufträge")
            tbl = pd.DataFrame({
                "Datum": p_df["award_date"].dt.date if "award_date" in p_df else None,
                "Titel": p_df["title"],
                "Empfänger": p_df["award_companies"].apply(lambda x: ", ".join(x)),
                "Vergeber": p_df["proc_office"],
                "Kanton": p_df["canton"],
                "Summe (CHF)": p_df["award_price"],
                "Anbieter": p_df["nr_of_offers"],
                "Verfahren": p_df["process_type"],
                "Auf simap.ch öffnen": p_df["project_id"].apply(make_simap_link),
            }).sort_values("Datum", ascending=False)
            st.dataframe(
                tbl, use_container_width=True, hide_index=True,
                column_config={
                    "Auf simap.ch öffnen": st.column_config.LinkColumn(
                        display_text="↗ Öffnen"),
                    "Summe (CHF)": st.column_config.NumberColumn(format="%.2f"),
                },
            )

            # Zeitreihe
            st.subheader("Zuschlagsvolumen über Zeit (Quartal)")
            ts = p_df.dropna(subset=["award_date"]).copy()
            if not ts.empty:
                ts["Periode"] = ts["award_date"].dt.to_period("Q").dt.to_timestamp()
                agg = ts.groupby("Periode").agg(
                    Anzahl=("award_date", "size"),
                    Summe_CHF=("award_price", "sum"),
                ).reset_index()
                ts_left, ts_right = st.columns(2)
                ts_left.caption("Anzahl Zuschläge pro Quartal")
                ts_left.bar_chart(agg.set_index("Periode")["Anzahl"])
                ts_right.caption("Volumen pro Quartal (CHF)")
                ts_right.bar_chart(agg.set_index("Periode")["Summe_CHF"])

            # Beziehung: je nach Filter unterschiedliche Aggregate
            if has_company and has_office:
                st.subheader("Empfänger–Vergeber-Matrix")
                ex = p_df.explode("award_companies").copy()
                ex = ex[ex["award_companies"].notna() & (ex["award_companies"] != "")]
                cross = ex.groupby(["award_companies", "proc_office"]).agg(
                    Zuschlaege=("project_id", "count"),
                    Summe_CHF=("award_price", "sum"),
                ).reset_index().sort_values("Summe_CHF", ascending=False)
                cross.columns = ["Empfänger", "Vergeber", "Zuschläge", "Summe_CHF"]
                st.dataframe(cross, use_container_width=True, hide_index=True)
            elif has_company:
                st.subheader("Top-Vergeber für diese(n) Empfänger")
                st.caption("Bei welchen Beschaffungsstellen war der Empfänger erfolgreich.")
                off_agg = p_df.groupby("proc_office").agg(
                    Zuschlaege=("project_id", "count"),
                    Summe_CHF=("award_price", "sum"),
                ).reset_index().sort_values("Summe_CHF", ascending=False).head(20)
                off_agg.columns = ["Vergeber", "Zuschläge", "Summe_CHF"]
                st.dataframe(off_agg, use_container_width=True, hide_index=True)
                if not off_agg.empty:
                    st.bar_chart(off_agg.set_index("Vergeber")["Summe_CHF"].head(15))
            elif has_office:
                st.subheader("Top-Empfänger dieses Vergebers")
                st.caption("Welche Firmen erhalten am meisten von dieser Stelle.")
                ex = p_df.explode("award_companies").copy()
                ex = ex[ex["award_companies"].notna() & (ex["award_companies"] != "")]
                firm_agg = ex.groupby("award_companies").agg(
                    Zuschlaege=("project_id", "count"),
                    Summe_CHF=("award_price", "sum"),
                ).reset_index().sort_values("Summe_CHF", ascending=False).head(20)
                firm_agg.columns = ["Empfänger", "Zuschläge", "Summe_CHF"]
                st.dataframe(firm_agg, use_container_width=True, hide_index=True)
                if not firm_agg.empty:
                    st.bar_chart(firm_agg.set_index("Empfänger")["Summe_CHF"].head(15))

            # CSV-Export
            csv = tbl.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "⬇ CSV (Anbieter & Vergeber)", csv,
                "simapnalytics_partners.csv", "text/csv",
            )


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
