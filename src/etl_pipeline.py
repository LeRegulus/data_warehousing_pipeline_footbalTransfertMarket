"""
Pipeline ETL - Data Warehouse Football (Transfermarkt)
Extraction -> Contrôle Qualité -> Transformation -> Chargement (PostgreSQL, schéma dw_foot)

Fichiers sources utilisés : players.csv, clubs.csv, competitions.csv,
appearances.csv, transfers.csv, player_valuations.csv
(games.csv, game_events.csv, club_games.csv, countries.csv, national_teams.csv,
 game_lineups.csv sont hors périmètre — cf. rapport section "Périmètre")

Usage:
    python etl_pipeline.py --data-dir data/ --db-url postgresql://user:pass@localhost:5432/dw --today 2026-08-21
"""

import argparse
import logging
import os
from datetime import datetime
import pandas as pd
import numpy as np
from sqlalchemy import create_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# 1. EXTRACTION
# ----------------------------------------------------------------------
def extract(data_dir: str) -> dict:
    files = ["players", "clubs", "competitions", "appearances", "transfers", "player_valuations"]
    dfs = {}
    for f in files:
        path = f"{data_dir}/{f}.csv"
        log.info(f"Lecture: {path}")
        dfs[f] = pd.read_csv(path)
        log.info(f"  -> {len(dfs[f])} lignes")
    return dfs


# ----------------------------------------------------------------------
# 2. CONTROLE QUALITE
# ----------------------------------------------------------------------
def check_types_numeriques(df: pd.DataFrame, colonnes: list) -> dict:
    """Compte, par colonne censée être numérique, les valeurs non vides qui ne se
    convertissent pas proprement en nombre (type irrégulier côté source)."""
    issues = {}
    for col in colonnes:
        if col not in df.columns:
            continue
        brut_present = df[col].notna() & (df[col].astype(str).str.strip() != "")
        coerce = pd.to_numeric(df[col], errors="coerce")
        nb_invalide = int((brut_present & coerce.isna()).sum())
        if nb_invalide:
            issues[col] = nb_invalide
    return issues


def check_types_dates(df: pd.DataFrame, colonnes: list) -> dict:
    """Compte, par colonne censée être une date, les valeurs non vides qui ne se
    convertissent pas proprement en date (format irrégulier côté source)."""
    issues = {}
    for col in colonnes:
        if col not in df.columns:
            continue
        brut_present = df[col].notna() & (df[col].astype(str).str.strip() != "")
        coerce = pd.to_datetime(df[col], errors="coerce")
        nb_invalide = int((brut_present & coerce.isna()).sum())
        if nb_invalide:
            issues[col] = nb_invalide
    return issues


def run_quality_checks(dfs: dict, today: pd.Timestamp) -> dict:
    report = {}

    apps = dfs["appearances"]
    comps = dfs["competitions"]
    orphan_comp = set(apps["competition_id"].unique()) - set(comps["competition_id"].unique())
    report["appearances_competition_id_orphelins"] = {
        "nb_codes": len(orphan_comp),
        "nb_lignes": int(apps["competition_id"].isin(orphan_comp).sum()),
        "pct_lignes": round(100 * apps["competition_id"].isin(orphan_comp).mean(), 2),
    }
    report["appearances_doublons"] = int(apps.duplicated(subset=["appearance_id"]).sum())

    tr = dfs["transfers"].copy()
    tr["transfer_date"] = pd.to_datetime(tr["transfer_date"], errors="coerce")
    report["transferts_dates_futures"] = int((tr["transfer_date"] > today).sum())
    report["transferts_fee_manquant_pct"] = round(100 * tr["transfer_fee"].isna().mean(), 2)

    players = dfs["players"]
    report["players_valeur_marchande_manquante_pct"] = round(100 * players["market_value_in_eur"].isna().mean(), 2)
    report["players_pied_manquant_pct"] = round(100 * players["foot"].isna().mean(), 2)

    clubs = dfs["clubs"]
    report["clubs_total_market_value_manquant_pct"] = round(100 * clubs["total_market_value"].isna().mean(), 2)

    # Types irréguliers : valeurs non vides qui ne se convertissent pas dans le type attendu
    types_numeriques = {}
    types_numeriques.update(check_types_numeriques(
        players, ["height_in_cm", "market_value_in_eur", "highest_market_value_in_eur"]))
    types_numeriques.update(check_types_numeriques(
        clubs, ["squad_size", "average_age", "foreigners_number"]))
    types_numeriques.update(check_types_numeriques(
        apps, ["goals", "assists", "yellow_cards", "red_cards", "minutes_played"]))
    types_numeriques.update(check_types_numeriques(
        dfs["transfers"], ["transfer_fee", "market_value_in_eur"]))
    types_numeriques.update(check_types_numeriques(
        dfs["player_valuations"], ["market_value_in_eur"]))
    report["types_numeriques_irreguliers"] = types_numeriques

    types_dates = {}
    types_dates.update(check_types_dates(players, ["date_of_birth"]))
    types_dates.update(check_types_dates(apps, ["date"]))
    types_dates.update(check_types_dates(dfs["transfers"], ["transfer_date"]))
    types_dates.update(check_types_dates(dfs["player_valuations"], ["date"]))
    report["types_dates_irreguliers"] = types_dates

    log.info(f"Rapport qualité: {report}")
    return report


# ----------------------------------------------------------------------
# 3. TRANSFORMATION - DIMENSIONS
# ----------------------------------------------------------------------
def saison_football(date: pd.Timestamp) -> str:
    if pd.isna(date):
        return None
    y = date.year
    return f"{y}/{y+1}" if date.month >= 7 else f"{y-1}/{y}"


def build_dim_date(all_dates: pd.Series) -> pd.DataFrame:
    dates = pd.to_datetime(all_dates.dropna().unique())
    dim = pd.DataFrame({"date_complete": sorted(dates)})
    dim["jour"] = dim["date_complete"].dt.day
    dim["mois"] = dim["date_complete"].dt.month
    dim["trimestre"] = dim["date_complete"].dt.quarter
    dim["annee"] = dim["date_complete"].dt.year
    dim["saison_football"] = dim["date_complete"].apply(saison_football)
    dim.insert(0, "id_date", range(1, len(dim) + 1))
    return dim


def build_dim_competition(comps: pd.DataFrame) -> pd.DataFrame:
    dim = comps[["competition_id", "name", "type", "confederation"]].rename(columns={
        "competition_id": "id_competition", "name": "nom",
    }).drop_duplicates(subset=["id_competition"])
    return dim


def build_dim_club(clubs: pd.DataFrame, valid_competitions: set) -> pd.DataFrame:
    dim = clubs[["club_id", "name", "stadium_name", "squad_size", "average_age", "domestic_competition_id"]].copy()
    dim = dim.rename(columns={
        "club_id": "id_club", "name": "nom", "stadium_name": "stade",
        "squad_size": "taille_effectif", "average_age": "age_moyen",
        "domestic_competition_id": "competition_domestique",
    })
    # Intégrité référentielle : si la compétition domestique n'existe pas dans Dim_Competition, on met NULL
    dim.loc[~dim["competition_domestique"].isin(valid_competitions), "competition_domestique"] = None
    dim = dim.drop_duplicates(subset=["id_club"])
    return dim


def tranche_age(age: float) -> str:
    if pd.isna(age):
        return "Inconnu"
    if age < 21:
        return "U21"
    if age < 25:
        return "21-24"
    if age < 29:
        return "25-28"
    if age < 33:
        return "29-32"
    return "33+"


def build_dim_joueur(players: pd.DataFrame, today: pd.Timestamp) -> pd.DataFrame:
    dim = players[[
        "player_id", "name", "position", "sub_position", "foot", "height_in_cm",
        "date_of_birth", "country_of_birth", "country_of_citizenship",
        "market_value_in_eur", "highest_market_value_in_eur",
    ]].copy()
    dim = dim.rename(columns={
        "player_id": "id_joueur", "name": "nom", "sub_position": "sous_position",
        "foot": "pied", "height_in_cm": "taille_cm", "date_of_birth": "date_naissance",
        "country_of_birth": "pays_naissance", "country_of_citizenship": "nationalite",
        "market_value_in_eur": "valeur_marchande_actuelle",
        "highest_market_value_in_eur": "valeur_marchande_max",
    })
    dim["date_naissance"] = pd.to_datetime(dim["date_naissance"], errors="coerce")
    age = (today - dim["date_naissance"]).dt.days / 365.25
    dim["tranche_age"] = age.apply(tranche_age)
    dim = dim.drop_duplicates(subset=["id_joueur"])
    return dim


# ----------------------------------------------------------------------
# 3. TRANSFORMATION - FAITS
# ----------------------------------------------------------------------
def build_fact_performances(apps: pd.DataFrame, dim_date, dim_joueur, dim_club, dim_competition) -> pd.DataFrame:
    df = apps.copy()
    df = df.drop_duplicates(subset=["appearance_id"])
    # errors="coerce" : cohérent avec le calcul de dim_date dans main() (même règle partout)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    n_date_invalide = df["date"].isna().sum()
    if n_date_invalide:
        log.warning(f"fact_performances: {n_date_invalide} ligne(s) avec date illisible, exclue(s)")
    df = df[df["date"].notna()]

    # Règle qualité : competition_id orphelin -> NULL (conservé dans le fait, exclu des ventilations par compétition)
    df.loc[~df["competition_id"].isin(dim_competition["id_competition"]), "competition_id"] = None
    # Règle qualité : club orphelin -> NULL
    df.loc[~df["player_club_id"].isin(dim_club["id_club"]), "player_club_id"] = None
    # Règle qualité : joueur orphelin -> ligne exclue (violerait la FK obligatoire)
    df = df[df["player_id"].isin(dim_joueur["id_joueur"])]

    df = df.merge(dim_date[["id_date", "date_complete"]], left_on="date", right_on="date_complete", how="left")
    n_sans_date = df["id_date"].isna().sum()
    if n_sans_date:
        log.warning(f"fact_performances: {n_sans_date} ligne(s) sans correspondance dans dim_date, exclue(s)")
    df = df[df["id_date"].notna()]
    df["id_date"] = df["id_date"].astype(int)

    fact = df[[
        "appearance_id", "id_date", "player_id", "player_club_id", "competition_id",
        "game_id", "goals", "assists", "yellow_cards", "red_cards", "minutes_played",
    ]].rename(columns={
        "appearance_id": "id_performance", "player_id": "id_joueur", "player_club_id": "id_club",
        "competition_id": "id_competition", "game_id": "id_match", "goals": "buts",
        "assists": "passes_decisives", "yellow_cards": "cartons_jaunes",
        "red_cards": "cartons_rouges", "minutes_played": "minutes_jouees",
    })
    return fact


def build_fact_transferts(transfers: pd.DataFrame, dim_date, dim_joueur, dim_club, today: pd.Timestamp) -> pd.DataFrame:
    df = transfers.copy()
    df["transfer_date"] = pd.to_datetime(df["transfer_date"], errors="coerce")

    # Règle qualité : dates de transfert futures (> date d'extraction) exclues de l'analyse temporelle
    # (probables fins de prêt mal qualifiées côté source) — documenté dans le rapport
    df = df[df["transfer_date"] <= today]
    df = df[df["transfer_date"].notna()]

    df = df[df["player_id"].isin(dim_joueur["id_joueur"])]
    df.loc[~df["from_club_id"].isin(dim_club["id_club"]), "from_club_id"] = None
    df.loc[~df["to_club_id"].isin(dim_club["id_club"]), "to_club_id"] = None

    df = df.merge(dim_date[["id_date", "date_complete"]], left_on="transfer_date", right_on="date_complete", how="left")
    n_sans_date = df["id_date"].isna().sum()
    if n_sans_date:
        log.warning(f"fact_transferts: {n_sans_date} ligne(s) sans correspondance dans dim_date, exclue(s)")
    df = df[df["id_date"].notna()]
    df["id_date"] = df["id_date"].astype(int)

    fact = df[[
        "id_date", "player_id", "from_club_id", "to_club_id",
        "transfer_season", "transfer_fee", "market_value_in_eur",
    ]].rename(columns={
        "player_id": "id_joueur", "from_club_id": "id_club_origine", "to_club_id": "id_club_destination",
        "transfer_season": "saison_transfert", "transfer_fee": "montant_transfert",
        "market_value_in_eur": "valeur_marchande_estimee",
    })
    return fact


def build_fact_valorisations(valuations: pd.DataFrame, dim_date, dim_joueur, dim_club) -> pd.DataFrame:
    df = valuations.copy()
    # errors="coerce" : cohérent avec le calcul de dim_date dans main() (même règle partout)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    n_date_invalide = df["date"].isna().sum()
    if n_date_invalide:
        log.warning(f"fact_valorisations: {n_date_invalide} ligne(s) avec date illisible, exclue(s)")
    df = df.dropna(subset=["date", "market_value_in_eur"])
    df = df[df["player_id"].isin(dim_joueur["id_joueur"])]
    df.loc[~df["current_club_id"].isin(dim_club["id_club"]), "current_club_id"] = None

    df = df.merge(dim_date[["id_date", "date_complete"]], left_on="date", right_on="date_complete", how="left")
    n_sans_date = df["id_date"].isna().sum()
    if n_sans_date:
        log.warning(f"fact_valorisations: {n_sans_date} ligne(s) sans correspondance dans dim_date, exclue(s)")
    df = df[df["id_date"].notna()]
    df["id_date"] = df["id_date"].astype(int)

    fact = df[["id_date", "player_id", "current_club_id", "market_value_in_eur"]].rename(columns={
        "player_id": "id_joueur", "current_club_id": "id_club", "market_value_in_eur": "valeur_marchande",
    })
    return fact


# ----------------------------------------------------------------------
# 4. CHARGEMENT
# ----------------------------------------------------------------------
def load(engine, dim_date, dim_competition, dim_club, dim_joueur, fact_perf, fact_trans, fact_val):
    with engine.begin() as conn:
        for table in ["fact_performances", "fact_transferts", "fact_valorisations",
                      "dim_club", "dim_joueur", "dim_date", "dim_competition"]:
            conn.exec_driver_sql(f"TRUNCATE TABLE dw_foot.{table} RESTART IDENTITY CASCADE;")

    dim_date.to_sql("dim_date", engine, schema="dw_foot", if_exists="append", index=False, chunksize=5000, method="multi")
    dim_competition.to_sql("dim_competition", engine, schema="dw_foot", if_exists="append", index=False, chunksize=5000, method="multi")
    dim_club.to_sql("dim_club", engine, schema="dw_foot", if_exists="append", index=False, chunksize=5000, method="multi")
    dim_joueur.to_sql("dim_joueur", engine, schema="dw_foot", if_exists="append", index=False, chunksize=5000, method="multi")
    fact_perf.to_sql("fact_performances", engine, schema="dw_foot", if_exists="append", index=False, chunksize=5000)
    fact_trans.to_sql("fact_transferts", engine, schema="dw_foot", if_exists="append", index=False, chunksize=5000)
    fact_val.to_sql("fact_valorisations", engine, schema="dw_foot", if_exists="append", index=False, chunksize=5000)
    log.info("Chargement terminé (schéma dw_foot).")


# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True, help="Dossier contenant les CSV sources")
    parser.add_argument("--db-url", default=None,
                         help="URL SQLAlchemy PostgreSQL (sinon variable d'environnement DW_DB_URL)")
    parser.add_argument("--today", default=None, help="Date de référence AAAA-MM-JJ (def: date du jour)")
    args = parser.parse_args()

    db_url = args.db_url or os.environ.get("DW_DB_URL")
    if not db_url:
        parser.error("--db-url requis (ou variable d'environnement DW_DB_URL) — évite de mettre le mot de passe "
                     "en argument visible dans l'historique shell/process list, préfère DW_DB_URL")

    today = pd.Timestamp(args.today) if args.today else pd.Timestamp(datetime.now().date())

    dfs = extract(args.data_dir)
    quality_report = run_quality_checks(dfs, today)

    dim_competition = build_dim_competition(dfs["competitions"])
    dim_club = build_dim_club(dfs["clubs"], set(dim_competition["id_competition"]))
    dim_joueur = build_dim_joueur(dfs["players"], today)

    all_dates = pd.concat([
        pd.to_datetime(dfs["appearances"]["date"], errors="coerce"),
        pd.to_datetime(dfs["transfers"]["transfer_date"], errors="coerce").pipe(lambda s: s[s <= today]),
        pd.to_datetime(dfs["player_valuations"]["date"], errors="coerce"),
    ])
    dim_date = build_dim_date(all_dates)

    fact_perf = build_fact_performances(dfs["appearances"], dim_date, dim_joueur, dim_club, dim_competition)
    fact_trans = build_fact_transferts(dfs["transfers"], dim_date, dim_joueur, dim_club, today)
    fact_val = build_fact_valorisations(dfs["player_valuations"], dim_date, dim_joueur, dim_club)

    log.info(f"Fact_Performances: {len(fact_perf)} lignes")
    log.info(f"Fact_Transferts: {len(fact_trans)} lignes")
    log.info(f"Fact_Valorisations: {len(fact_val)} lignes")

    engine = create_engine(db_url)
    load(engine, dim_date, dim_competition, dim_club, dim_joueur, fact_perf, fact_trans, fact_val)

    log.info("Pipeline terminé avec succès.")
    log.info(f"Rapport qualité (à mettre dans le rapport) : {quality_report}")


if __name__ == "__main__":
    main()
