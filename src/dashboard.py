"""
Dashboard interactif - Data Warehouse Football (Transfermarkt)
Lancer avec: streamlit run dashboard.py -- --db-url postgresql://user:pass@localhost:5432/dw
"""

import os
import sys
import pandas as pd
import streamlit as st
import plotly.express as px
from sqlalchemy import create_engine

st.set_page_config(page_title="Dashboard Football Analytics", layout="wide")


def get_db_url():
    for i, arg in enumerate(sys.argv):
        if arg == "--db-url" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    # Préférer la variable d'environnement / st.secrets à un mot de passe en argument CLI visible
    env_url = os.environ.get("DW_DB_URL")
    if env_url:
        return env_url
    return st.secrets.get("db_url", "postgresql://user:pass@localhost:5432/dw")


@st.cache_resource
def get_engine(db_url):
    return create_engine(db_url)


engine = get_engine(get_db_url())

st.title("⚽ Dashboard Football Analytics — Transfermarkt")

saisons = pd.read_sql(
    "SELECT DISTINCT saison_football FROM dw_foot.dim_date WHERE saison_football IS NOT NULL ORDER BY 1 DESC",
    engine,
)["saison_football"].tolist()

if not saisons:
    st.warning(
        "Aucune donnée dans dw_foot (dim_date vide). "
        "Lance d'abord le pipeline ETL : `python src/etl_pipeline.py --data-dir data --db-url ...`"
    )
    st.stop()

saison_select = st.selectbox("Saison", saisons, index=0)

# --- KPIs ---
kpi = pd.read_sql(
    """
    SELECT COUNT(DISTINCT f.id_joueur) AS nb_joueurs, SUM(f.buts) AS buts, COUNT(DISTINCT f.id_match) AS nb_matchs
    FROM dw_foot.fact_performances f
    JOIN dw_foot.dim_date d ON f.id_date = d.id_date
    WHERE d.saison_football = %(saison)s
    """, engine, params={"saison": saison_select}).iloc[0]
kpi = kpi.fillna(0)  # aucune ligne pour la saison -> SUM/COUNT renvoient NULL côté SQL
col1, col2, col3 = st.columns(3)
col1.metric("Joueurs actifs", int(kpi["nb_joueurs"]))
col2.metric("Buts marqués", int(kpi["buts"]))
col3.metric("Matchs couverts", int(kpi["nb_matchs"]))

st.divider()

# Q1 - Valeur marchande par poste et tranche d'âge
st.subheader("Q1 — Valeur marchande moyenne par poste et tranche d'âge")
q1 = pd.read_sql("""
    WITH derniere_valo AS (
        SELECT DISTINCT ON (id_joueur) id_joueur, valeur_marchande
        FROM dw_foot.fact_valorisations ORDER BY id_joueur, id_date DESC
    )
    SELECT j.position, j.tranche_age, AVG(v.valeur_marchande) AS valeur_moy
    FROM derniere_valo v JOIN dw_foot.dim_joueur j ON v.id_joueur = j.id_joueur
    WHERE j.position IS NOT NULL AND j.position != 'Missing'
    GROUP BY j.position, j.tranche_age
""", engine)
fig1 = px.bar(q1, x="tranche_age", y="valeur_moy", color="position", barmode="group",
              category_orders={"tranche_age": ["U21", "21-24", "25-28", "29-32", "33+", "Inconnu"]})
st.plotly_chart(fig1, use_container_width=True)

# Q2 - Top buteurs+passeurs
st.subheader("Q2 — Top 10 buteurs + passeurs de la saison")
q2 = pd.read_sql(
    """
    SELECT j.nom, SUM(f.buts) AS buts, SUM(f.passes_decisives) AS passes
    FROM dw_foot.fact_performances f
    JOIN dw_foot.dim_date d ON f.id_date = d.id_date
    JOIN dw_foot.dim_joueur j ON f.id_joueur = j.id_joueur
    WHERE d.saison_football = %(saison)s
    GROUP BY j.nom ORDER BY (SUM(f.buts) + SUM(f.passes_decisives)) DESC LIMIT 10
    """, engine, params={"saison": saison_select})
fig2 = px.bar(q2, x="nom", y=["buts", "passes"], barmode="stack")
st.plotly_chart(fig2, use_container_width=True)

# Q3 - Ecart transfert / valeur marchande
st.subheader("Q3 — Transferts : écart montant payé vs valeur marchande estimée")
q3 = pd.read_sql("""
    SELECT j.nom, t.montant_transfert, t.valeur_marchande_estimee,
           (t.montant_transfert - t.valeur_marchande_estimee) AS ecart
    FROM dw_foot.fact_transferts t JOIN dw_foot.dim_joueur j ON t.id_joueur = j.id_joueur
    WHERE t.montant_transfert IS NOT NULL AND t.valeur_marchande_estimee IS NOT NULL AND t.montant_transfert > 0
    ORDER BY ecart DESC LIMIT 10
""", engine)
fig3 = px.bar(q3, x="nom", y="ecart", title="Top 10 des transferts les plus au-dessus de la valeur estimée")
st.plotly_chart(fig3, use_container_width=True)

# Q4 - Cartons par poste
st.subheader("Q4 — Discipline (cartons) par poste")
q4 = pd.read_sql("""
    SELECT j.position, SUM(f.cartons_jaunes) AS jaunes, SUM(f.cartons_rouges) AS rouges,
           ROUND(SUM(f.cartons_jaunes)::numeric / NULLIF(COUNT(*),0), 3) AS jaunes_par_match
    FROM dw_foot.fact_performances f JOIN dw_foot.dim_joueur j ON f.id_joueur = j.id_joueur
    WHERE j.position IS NOT NULL AND j.position != 'Missing'
    GROUP BY j.position ORDER BY jaunes_par_match DESC
""", engine)
fig4 = px.bar(q4, x="position", y="jaunes_par_match")
st.plotly_chart(fig4, use_container_width=True)

# Q5 - Clubs les plus actifs à l'achat
st.subheader("Q5 — Clubs les plus dépensiers (transferts entrants)")
q5 = pd.read_sql("""
    SELECT c.nom, COUNT(*) AS nb_recrues, SUM(t.montant_transfert) AS depense_totale
    FROM dw_foot.fact_transferts t JOIN dw_foot.dim_club c ON t.id_club_destination = c.id_club
    WHERE t.montant_transfert > 0
    GROUP BY c.nom ORDER BY depense_totale DESC LIMIT 10
""", engine)
fig5 = px.bar(q5, x="nom", y="depense_totale", hover_data=["nb_recrues"])
st.plotly_chart(fig5, use_container_width=True)
