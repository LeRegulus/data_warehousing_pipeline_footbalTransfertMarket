"""
Tests du pipeline ETL football. Lancer avec: pytest tests/
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
from etl_pipeline import (
    saison_football, tranche_age, build_dim_date, build_dim_competition,
    build_dim_club, build_dim_joueur, build_fact_performances,
    build_fact_transferts, build_fact_valorisations,
)

TODAY = pd.Timestamp("2026-08-21")


def test_saison_football_avant_juillet():
    assert saison_football(pd.Timestamp("2024-03-15")) == "2023/2024"


def test_saison_football_apres_juillet():
    assert saison_football(pd.Timestamp("2024-09-01")) == "2024/2025"


def test_tranche_age_buckets():
    assert tranche_age(19) == "U21"
    assert tranche_age(23) == "21-24"
    assert tranche_age(35) == "33+"
    assert tranche_age(None) == "Inconnu"


def make_players():
    return pd.DataFrame([
        {"player_id": 1, "name": "Joueur A", "position": "Attack", "sub_position": "Centre-Forward",
         "foot": "right", "height_in_cm": 180, "date_of_birth": "2000-01-01",
         "country_of_birth": "France", "country_of_citizenship": "France",
         "market_value_in_eur": 5000000, "highest_market_value_in_eur": 8000000},
        {"player_id": 2, "name": "Joueur B", "position": "Defender", "sub_position": "Centre-Back",
         "foot": None, "height_in_cm": 190, "date_of_birth": "1995-06-15",
         "country_of_birth": "Sénégal", "country_of_citizenship": "Sénégal",
         "market_value_in_eur": None, "highest_market_value_in_eur": 3000000},
    ])


def make_clubs():
    return pd.DataFrame([
        {"club_id": 10, "name": "Club X", "stadium_name": "Stade X", "squad_size": 25,
         "average_age": 26.0, "domestic_competition_id": "FR1"},
        {"club_id": 20, "name": "Club Y", "stadium_name": "Stade Y", "squad_size": 24,
         "average_age": 27.0, "domestic_competition_id": "INEXISTANT"},  # compétition orpheline
    ])


def make_competitions():
    return pd.DataFrame([{"competition_id": "FR1", "name": "Ligue 1", "type": "domestic_league", "confederation": "europa"}])


def test_dim_club_gere_competition_orpheline():
    comps = make_competitions()
    dim_comp = build_dim_competition(comps)
    dim_club = build_dim_club(make_clubs(), set(dim_comp["id_competition"]))
    club_y = dim_club[dim_club["id_club"] == 20].iloc[0]
    assert pd.isna(club_y["competition_domestique"])  # FK orpheline mise à NULL, pas d'erreur


def test_dim_joueur_colonnes_renommees():
    dim = build_dim_joueur(make_players(), TODAY)
    assert "pied" in dim.columns  # anciennement "foot" côté source
    assert "nom" in dim.columns
    assert dim.loc[dim["id_joueur"] == 1, "tranche_age"].iloc[0] != "Inconnu"


def test_fact_performances_exclut_joueur_orphelin():
    apps = pd.DataFrame([
        {"appearance_id": "a1", "game_id": 100, "player_id": 1, "player_club_id": 10,
         "player_current_club_id": 10, "date": "2024-09-01", "player_name": "Joueur A",
         "competition_id": "FR1", "yellow_cards": 1, "red_cards": 0, "goals": 2, "assists": 1, "minutes_played": 90},
        {"appearance_id": "a2", "game_id": 101, "player_id": 999, "player_club_id": 10,  # joueur inconnu
         "player_current_club_id": 10, "date": "2024-09-02", "player_name": "Inconnu",
         "competition_id": "FR1", "yellow_cards": 0, "red_cards": 0, "goals": 0, "assists": 0, "minutes_played": 45},
    ])
    dim_comp = build_dim_competition(make_competitions())
    dim_club = build_dim_club(make_clubs(), set(dim_comp["id_competition"]))
    dim_joueur = build_dim_joueur(make_players(), TODAY)
    dim_date = build_dim_date(pd.to_datetime(apps["date"]))

    fact = build_fact_performances(apps, dim_date, dim_joueur, dim_club, dim_comp)
    assert len(fact) == 1  # la ligne au joueur 999 (orphelin) est exclue
    assert fact.iloc[0]["buts"] == 2


def test_fact_transferts_exclut_dates_futures():
    transfers = pd.DataFrame([
        {"player_id": 1, "transfer_date": "2024-07-01", "transfer_season": "24/25",
         "from_club_id": 10, "to_club_id": 20, "transfer_fee": 1000000, "market_value_in_eur": 900000, "player_name": "Joueur A"},
        {"player_id": 1, "transfer_date": "2030-07-01", "transfer_season": "29/30",  # date future suspecte
         "from_club_id": 20, "to_club_id": 10, "transfer_fee": 2000000, "market_value_in_eur": 1800000, "player_name": "Joueur A"},
    ])
    dim_comp = build_dim_competition(make_competitions())
    dim_club = build_dim_club(make_clubs(), set(dim_comp["id_competition"]))
    dim_joueur = build_dim_joueur(make_players(), TODAY)
    dim_date = build_dim_date(pd.to_datetime(transfers["transfer_date"]).pipe(lambda s: s[s <= TODAY]))

    fact = build_fact_transferts(transfers, dim_date, dim_joueur, dim_club, TODAY)
    assert len(fact) == 1
    assert fact.iloc[0]["montant_transfert"] == 1000000


def test_fact_valorisations_ignore_valeurs_nulles():
    val = pd.DataFrame([
        {"player_id": 1, "date": "2024-01-01", "market_value_in_eur": 5000000, "current_club_name": "Club X",
         "current_club_id": 10, "player_club_domestic_competition_id": "FR1"},
        {"player_id": 1, "date": "2024-06-01", "market_value_in_eur": None, "current_club_name": "Club X",
         "current_club_id": 10, "player_club_domestic_competition_id": "FR1"},
    ])
    dim_comp = build_dim_competition(make_competitions())
    dim_club = build_dim_club(make_clubs(), set(dim_comp["id_competition"]))
    dim_joueur = build_dim_joueur(make_players(), TODAY)
    dim_date = build_dim_date(pd.to_datetime(val["date"]))

    fact = build_fact_valorisations(val, dim_date, dim_joueur, dim_club)
    assert len(fact) == 1  # la ligne à valeur NULL est exclue


def test_fact_performances_exclut_date_illisible():
    apps = pd.DataFrame([
        {"appearance_id": "a1", "game_id": 100, "player_id": 1, "player_club_id": 10,
         "player_current_club_id": 10, "date": "2024-09-01", "player_name": "Joueur A",
         "competition_id": "FR1", "yellow_cards": 0, "red_cards": 0, "goals": 1, "assists": 0, "minutes_played": 90},
        {"appearance_id": "a2", "game_id": 101, "player_id": 1, "player_club_id": 10,  # date illisible
         "player_current_club_id": 10, "date": "pas-une-date", "player_name": "Joueur A",
         "competition_id": "FR1", "yellow_cards": 0, "red_cards": 0, "goals": 0, "assists": 0, "minutes_played": 45},
    ])
    dim_comp = build_dim_competition(make_competitions())
    dim_club = build_dim_club(make_clubs(), set(dim_comp["id_competition"]))
    dim_joueur = build_dim_joueur(make_players(), TODAY)
    dim_date = build_dim_date(pd.to_datetime(apps["date"], errors="coerce"))

    fact = build_fact_performances(apps, dim_date, dim_joueur, dim_club, dim_comp)
    assert len(fact) == 1  # la ligne à date illisible est exclue, pas de crash
    assert fact.iloc[0]["id_performance"] == "a1"


def test_fact_performances_exclut_ligne_sans_correspondance_dim_date():
    apps = pd.DataFrame([
        {"appearance_id": "a1", "game_id": 100, "player_id": 1, "player_club_id": 10,
         "player_current_club_id": 10, "date": "2024-09-01", "player_name": "Joueur A",
         "competition_id": "FR1", "yellow_cards": 0, "red_cards": 0, "goals": 1, "assists": 0, "minutes_played": 90},
    ])
    dim_comp = build_dim_competition(make_competitions())
    dim_club = build_dim_club(make_clubs(), set(dim_comp["id_competition"]))
    dim_joueur = build_dim_joueur(make_players(), TODAY)
    # dim_date construite sur une autre date -> le merge ne trouve aucune correspondance pour "2024-09-01"
    dim_date = build_dim_date(pd.to_datetime(pd.Series(["2020-01-01"])))

    fact = build_fact_performances(apps, dim_date, dim_joueur, dim_club, dim_comp)
    assert len(fact) == 0  # ligne exclue plutôt que d'insérer id_date=NULL en base
