"""SimApNALYTICS -- Ausschreibungs-/Zuschlagsanalyse (Streamlit).

Start:
    pip install -r requirements.txt
    streamlit run dashboard.py

Nutzt die OEFFENTLICHE simap-API (anonym, kein Login). Tabs:
  1. Suche      - Zuschlaege ueber freie Filter (Sidebar)
  2. Wer gewinnt- Ranking & Wettbewerb zur Suche
  3. Trends     - Volumen/CPV zur Suche
  4. Marktanalyse - eigene CPV-basierte Marktauswertung mit Rangliste
"""
from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from simapnalytics.api.client import SimapClient
from simapnalytics.analysis import analyzer as az

CANTONS = ["AG", "AI", "AR", "BE", "BL", "BS", "FR", "GE", "GL", "GR", "JU",
           "LU", "NE", "NW", "OW", "SG", "SH", "SO", "SZ", "TG", "TI", "UR",
           "VD", "VS", "ZG", "ZH"]
SUBTYPES = {"construction": "Bau", "service": "Dienstleistung", "supply": "Lieferung"}

st.set_page_config(page_title="SimApNALYTICS", layout="wide")
st.title("SimApNALYTICS")
st.caption("Ausschreibungs- und Zuschlagsanalyse  ·  öffentliche simap-API, kein Login")


@st.cache_data(show_spinner="Lade Zuschläge von simap (inkl. Details)…", ttl=3600)
def fetch_awards(search, cantons, cpv, von, bis, subtypes, max_n) -> pd.DataFrame:
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


# ===== Sidebar fuer Tabs 1-3 ============================================

with st.sidebar:
    st.header("Suchfilter (Tabs Suche/Gewinner/Trends)")
    f_search = st.text_input("Suchtext (min. 3 Zeichen)", placeholder="z.B. Sanierung")
    f_cantons = st.multiselect("Kantone", CANTONS)
    f_subtypes = st.multiselect("Projekttyp", list(SUBTYPES),
                                format_func=lambda k: SUBTYPES[k])
    f_cpv = st.text_input("CPV-Codes (8-stellig, Komma-getrennt)",
                          placeholder="71000000, 45233140")
    c1, c2 = st.columns(2)
    f_von = c1.text_input("Publ. ab", placeholder="2026-01-01")
    f_bis = c2.text_input("Publ. bis", placeholder="2026-12-31")
    f_max = st.slider("Max. Treffer", 20, 500, 100, step=20)
    go = st.button("Suchen", type="primary", use_container_width=True)
    st.divider()
    st.caption("Pro Zuschlag werden Detaildaten nachgeladen – grössere Mengen "
               "dauern entsprechend länger. Die Marktanalyse hat eigene Filter "
               "direkt im Tab.")


tab1, tab2, tab3, tab4 = st.tabs(
    ["Suche", "Wer gewinnt", "Trends", "Marktanalyse"]
)


# ===== Tab 1-3: an Sidebar-Filter gebunden =============================

if go:
    cpv_list = [c.strip() for c in f_cpv.split(",") if c.strip()]
    try:
        df = fetch_awards(f_search, f_cantons, cpv_list, f_von, f_bis, f_subtypes, f_max)
    except Exception as e:  # noqa: BLE001
        st.error(f"Fehler beim Abruf: {e}")
        df = pd.DataFrame()
else:
    df = pd.DataFrame()


with tab1:
    if not go:
        st.info("Stelle links die Filter ein und klicke **Suchen**.")
    elif df.empty:
        st.warning("Keine Zuschläge zu diesen Kriterien gefunden.")
    else:
        st.success(f"{len(df)} Zuschläge gefunden.")
        display = pd.DataFrame({
            "Titel": df["title"],
            "Kanton": df["canton"],
            "Beschaffungsstelle": df["proc_office"],
            "Zuschlagsempfänger": df["award_companies"].apply(lambda x: ", ".join(x)),
            "Zuschlagsdatum": df["award_date"].dt.date if "award_date" in df else None,
            "Summe": df["award_price"],
            "Währung": df["award_currency"],
            "Anbieter": df["nr_of_offers"],
            "Verfahren": df["process_type"],
        })
        st.dataframe(display, use_container_width=True, hide_index=True)
        csv = display.to_csv(index=False).encode("utf-8-sig")
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as xl:
            display.to_excel(xl, index=False, sheet_name="Zuschläge")
        st.download_button("CSV", csv, "simapnalytics_zuschlaege.csv", "text/csv")
        st.download_button("Excel", buf.getvalue(), "simapnalytics_zuschlaege.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

with tab2:
    if df.empty:
        st.caption("Bitte erst links suchen.")
    else:
        st.subheader("Ranking der Zuschlagsempfänger")
        ranking = az.winners_ranking(df, top=25)
        st.dataframe(ranking, use_container_width=True, hide_index=True)
        if not ranking.empty:
            st.bar_chart(ranking.set_index("Firma")["Summe_CHF"])
        st.subheader("Wettbewerbsdichte je Kanton")
        st.caption("Ø Anzahl Anbieter pro Zuschlag – tief = wenig Konkurrenz.")
        st.dataframe(az.competition_density(df), use_container_width=True, hide_index=True)

with tab3:
    if df.empty:
        st.caption("Bitte erst links suchen.")
    else:
        st.subheader("Volumen über Zeit (nach Zuschlagsdatum)")
        vol = az.volume_over_time(df, freq="ME")
        if not vol.empty:
            st.line_chart(vol.set_index("Periode")["Anzahl"])
        st.subheader("Häufigste CPV-Gruppen")
        st.dataframe(az.cpv_distribution(df, level=2, top=15),
                     use_container_width=True, hide_index=True)


# ===== Tab 4: Marktanalyse (eigene Filter) ==============================

with tab4:
    st.subheader("Marktanalyse nach CPV")
    st.caption("Wer beherrscht den Markt? Eingabe von CPV-Code(s) und Zeitraum "
               "liefert eine Rangliste der Anbieter mit allen ihren Aufträgen.")

    m1, m2, m3 = st.columns([2, 1, 1])
    m_cpv = m1.text_input("CPV-Codes (Komma-getrennt, mindestens einer)",
                          placeholder="30120000, 30232100",
                          key="market_cpv")
    m_von = m2.text_input("Publ. ab", value="2024-07-01", key="market_von")
    m_bis = m3.text_input("Publ. bis", value="", placeholder="leer = heute",
                          key="market_bis")
    m4, m5 = st.columns([1, 3])
    m_max = m4.number_input("Max. Treffer", min_value=50, max_value=2000,
                            value=500, step=50, key="market_max")
    m_go = m5.button("Marktanalyse starten", type="primary",
                     use_container_width=True, key="market_go")

    if not m_go:
        st.info("CPV eingeben (z. B. **30120000, 30232100** für Drucker/Kopierer) "
                "und Zeitraum wählen.")
    else:
        cpvs = [c.strip() for c in m_cpv.split(",") if c.strip()]
        if not cpvs:
            st.error("Mindestens ein CPV-Code nötig.")
            st.stop()
        try:
            with st.spinner(f"Lade Zuschläge für CPV {', '.join(cpvs)}…"):
                m_df = fetch_awards(None, None, cpvs, m_von or None,
                                    m_bis or None, None, int(m_max))
        except Exception as e:  # noqa: BLE001
            st.error(f"Fehler beim Abruf: {e}")
            st.stop()

        if m_df.empty:
            st.warning("Keine Zuschläge zu diesen CPV-Codes im Zeitraum gefunden.")
        else:
            # ---- KPI-Zeile ----
            total = m_df["award_price"].sum(skipna=True)
            n_total = len(m_df)
            n_with_price = m_df["award_price"].notna().sum()
            firms = m_df.explode("award_companies")["award_companies"]
            firms = firms[firms.notna() & (firms != "")]
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Zuschläge", n_total)
            k2.metric("Marktvolumen (CHF)", f"{total:,.0f}")
            k3.metric("Anbieter (unique)", firms.nunique())
            k4.metric("Davon mit Preis", f"{n_with_price}/{n_total}")
            if n_with_price < n_total:
                st.caption(f"Hinweis: Bei {n_total - n_with_price} Zuschlägen ist "
                           "keine Summe publiziert – diese fliessen in Anzahlen, "
                           "aber nicht ins Marktvolumen ein.")

            # ---- Rangliste ----
            st.subheader("Rangliste der Marktanteile")
            ranking = az.winners_ranking(m_df, top=50).copy()
            if not ranking.empty and total > 0:
                ranking.insert(1, "Rang", range(1, len(ranking) + 1))
                ranking["Marktanteil %"] = (
                    ranking["Summe_CHF"] / total * 100).round(2)
                st.dataframe(ranking[["Rang", "Firma", "Zuschlaege",
                                      "Summe_CHF", "Marktanteil %"]],
                             use_container_width=True, hide_index=True)
                st.bar_chart(ranking.set_index("Firma")["Summe_CHF"].head(15))
            else:
                st.dataframe(ranking, use_container_width=True, hide_index=True)

            # ---- Aufträge je Firma (aufklappbar) ----
            st.subheader("Aufträge je Firma")
            st.caption("Pro Firma alle gewonnenen Aufträge im Zeitraum.")
            companies_sorted = (ranking["Firma"].tolist()
                                if not ranking.empty else [])
            for firma in companies_sorted:
                rows = m_df[m_df["award_companies"].apply(lambda x: firma in (x or []))]
                if rows.empty:
                    continue
                summe = rows["award_price"].sum(skipna=True)
                with st.expander(
                    f"{firma}  ·  {len(rows)} Auftrag/Aufträge  ·  "
                    f"CHF {summe:,.2f}"
                ):
                    tbl = pd.DataFrame({
                        "Datum": rows["award_date"].dt.date,
                        "Titel": rows["title"],
                        "Stelle": rows["proc_office"],
                        "Kanton": rows["canton"],
                        "Summe (CHF)": rows["award_price"],
                        "Anbieter": rows["nr_of_offers"],
                        "Verfahren": rows["process_type"],
                    }).sort_values("Datum", ascending=False)
                    st.dataframe(tbl, use_container_width=True, hide_index=True)

            # ---- Zeitreihe ----
            st.subheader("Marktvolumen über Zeit")
            ts = m_df.dropna(subset=["award_date"]).copy()
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

            # ---- Export ----
            st.subheader("Export")
            export = pd.DataFrame({
                "Datum": m_df["award_date"].dt.date,
                "Titel": m_df["title"],
                "Empfänger": m_df["award_companies"].apply(lambda x: ", ".join(x)),
                "Summe_CHF": m_df["award_price"],
                "Anbieter": m_df["nr_of_offers"],
                "Kanton": m_df["canton"],
                "Stelle": m_df["proc_office"],
                "Verfahren": m_df["process_type"],
                "CPV": m_df["cpv"].apply(lambda x: ", ".join(x)),
            })
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as xl:
                export.to_excel(xl, index=False, sheet_name="Auftraege")
                if not ranking.empty:
                    ranking.to_excel(xl, index=False, sheet_name="Rangliste")
            st.download_button("Marktanalyse als Excel",
                               buf.getvalue(),
                               "simapnalytics_marktanalyse.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
