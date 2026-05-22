"""SimApNALYTICS -- Ausschreibungs-/Zuschlagsanalyse (Streamlit).

Start:
    pip install -r requirements.txt
    streamlit run dashboard.py

Nutzt die OEFFENTLICHE simap-API (anonym, kein Login). Filter links,
Resultate + Analysen rechts, Export als Excel/CSV.
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


with st.sidebar:
    st.header("Suchfilter")
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
    st.caption("Mindestens ein Filter nötig. Pro Zuschlag werden Detaildaten "
               "nachgeladen – grössere Mengen dauern entsprechend länger.")

if not go:
    st.info("Stelle links die Filter ein und klicke **Suchen**.")
    st.stop()

cpv_list = [c.strip() for c in f_cpv.split(",") if c.strip()]

try:
    df = fetch_awards(f_search, f_cantons, cpv_list, f_von, f_bis, f_subtypes, f_max)
except Exception as e:  # noqa: BLE001
    st.error(f"Fehler beim Abruf: {e}")
    st.stop()

if df.empty:
    st.warning("Keine Zuschläge zu diesen Kriterien gefunden.")
    st.stop()

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
    "Beschaffung Start": df["project_start"].dt.date if "project_start" in df else None,
    "Beschaffung Ende": df["project_end"].dt.date if "project_end" in df else None,
    "Verfahren": df["process_type"],
})

tab1, tab2, tab3 = st.tabs(["Resultate", "Wer gewinnt", "Trends"])

with tab1:
    st.dataframe(display, use_container_width=True, hide_index=True)
    csv = display.to_csv(index=False).encode("utf-8-sig")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        display.to_excel(xl, index=False, sheet_name="Zuschläge")
    st.download_button("CSV herunterladen", csv, "simapnalytics_zuschlaege.csv", "text/csv")
    st.download_button("Excel herunterladen", buf.getvalue(),
                       "simapnalytics_zuschlaege.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

with tab2:
    st.subheader("Ranking der Zuschlagsempfänger")
    ranking = az.winners_ranking(df, top=25)
    st.dataframe(ranking, use_container_width=True, hide_index=True)
    if not ranking.empty:
        st.bar_chart(ranking.set_index("Firma")["Summe_CHF"])
    st.subheader("Wettbewerbsdichte je Kanton")
    st.caption("Durchschnittliche Anzahl Anbieter pro Zuschlag – tief = wenig Konkurrenz.")
    st.dataframe(az.competition_density(df), use_container_width=True, hide_index=True)

with tab3:
    st.subheader("Volumen über Zeit (nach Zuschlagsdatum)")
    vol = az.volume_over_time(df, freq="ME")
    if not vol.empty:
        st.line_chart(vol.set_index("Periode")["Anzahl"])
    st.subheader("Häufigste CPV-Gruppen")
    st.dataframe(az.cpv_distribution(df, level=2, top=15),
                 use_container_width=True, hide_index=True)
