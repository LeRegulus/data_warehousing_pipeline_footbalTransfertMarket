"""
Génère un petit jeu de données synthétique au format Transfermarkt,
utile pour des tests rapides sans charger les fichiers complets.
Le vrai dataset (Kaggle "Football Data from Transfermarkt") doit être
placé dans ce dossier data/ pour l'exécution réelle du pipeline :
players.csv, clubs.csv, competitions.csv, appearances.csv,
transfers.csv, player_valuations.csv

Usage: python data/generate_synthetic.py
"""
import numpy as np
import pandas as pd
from pathlib import Path

rng = np.random.default_rng(0)
out = Path(__file__).parent

competitions = pd.DataFrame([
    {"competition_id": "FR1", "competition_code": "ligue-1", "name": "ligue 1",
     "sub_type": "first_tier", "type": "domestic_league", "country_id": 1,
     "country_name": "France", "domestic_league_code": "FR1", "confederation": "europa",
     "total_clubs": 18, "url": ""},
])
competitions.to_csv(out / "competitions.csv", index=False)

clubs = pd.DataFrame([
    {"club_id": 1, "club_code": "club-a", "name": "Club A", "domestic_competition_id": "FR1",
     "total_market_value": None, "squad_size": 25, "average_age": 26.0,
     "foreigners_number": 10, "foreigners_percentage": 40.0, "national_team_players": 3,
     "stadium_name": "Stade A", "stadium_seats": 20000, "net_transfer_record": "+€1m",
     "coach_name": "Coach A", "last_season": 2026, "filename": "", "url": ""},
    {"club_id": 2, "club_code": "club-b", "name": "Club B", "domestic_competition_id": "FR1",
     "total_market_value": None, "squad_size": 24, "average_age": 27.0,
     "foreigners_number": 8, "foreigners_percentage": 33.0, "national_team_players": 2,
     "stadium_name": "Stade B", "stadium_seats": 18000, "net_transfer_record": "-€2m",
     "coach_name": "Coach B", "last_season": 2026, "filename": "", "url": ""},
])
clubs.to_csv(out / "clubs.csv", index=False)

n_players = 30
players = pd.DataFrame({
    "player_id": range(1, n_players + 1),
    "first_name": [f"Prenom{i}" for i in range(n_players)],
    "last_name": [f"Nom{i}" for i in range(n_players)],
    "name": [f"Joueur {i}" for i in range(n_players)],
    "last_season": 2026,
    "current_club_id": rng.choice([1, 2], n_players),
    "player_code": [f"joueur-{i}" for i in range(n_players)],
    "country_of_birth": rng.choice(["France", "Senegal", "Brazil"], n_players),
    "city_of_birth": "Ville",
    "country_of_citizenship": rng.choice(["France", "Senegal", "Brazil"], n_players),
    "date_of_birth": pd.to_datetime("2000-01-01") - pd.to_timedelta(rng.integers(0, 15*365, n_players), unit="D"),
    "sub_position": rng.choice(["Centre-Forward", "Centre-Back", "Central Midfield", "Goalkeeper"], n_players),
    "position": rng.choice(["Attack", "Defender", "Midfield", "Goalkeeper"], n_players),
    "foot": rng.choice(["right", "left", None], n_players),
    "height_in_cm": rng.integers(170, 200, n_players),
    "contract_expiration_date": None, "agent_name": None, "image_url": None,
    "international_caps": None, "international_goals": None, "current_national_team_id": None,
    "url": "", "current_club_domestic_competition_id": "FR1", "current_club_name": "Club A",
    "market_value_in_eur": rng.choice([1_000_000, 5_000_000, None], n_players),
    "highest_market_value_in_eur": rng.integers(1_000_000, 10_000_000, n_players),
})
players.to_csv(out / "players.csv", index=False)

n_apps = 300
appearances = pd.DataFrame({
    "appearance_id": [f"app{i}" for i in range(n_apps)],
    "game_id": rng.integers(1000, 1010, n_apps),
    "player_id": rng.integers(1, n_players + 1, n_apps),
    "player_club_id": rng.choice([1, 2], n_apps),
    "player_current_club_id": rng.choice([1, 2], n_apps),
    "date": pd.to_datetime("2024-08-01") + pd.to_timedelta(rng.integers(0, 300, n_apps), unit="D"),
    "player_name": "Joueur",
    "competition_id": rng.choice(["FR1", "XXXX"], n_apps),  # XXXX = orphelin volontaire
    "yellow_cards": rng.integers(0, 2, n_apps),
    "red_cards": rng.choice([0, 0, 0, 1], n_apps),
    "goals": rng.integers(0, 3, n_apps),
    "assists": rng.integers(0, 2, n_apps),
    "minutes_played": rng.integers(0, 91, n_apps),
})
appearances.to_csv(out / "appearances.csv", index=False)

n_tr = 40
transfers = pd.DataFrame({
    "player_id": rng.integers(1, n_players + 1, n_tr),
    "transfer_date": pd.to_datetime("2024-07-01") + pd.to_timedelta(rng.integers(-365, 365, n_tr), unit="D"),
    "transfer_season": "24/25",
    "from_club_id": rng.choice([1, 2], n_tr),
    "to_club_id": rng.choice([1, 2], n_tr),
    "from_club_name": "Club", "to_club_name": "Club",
    "transfer_fee": rng.choice([0, 1_000_000, 5_000_000, None], n_tr),
    "market_value_in_eur": rng.choice([1_000_000, 4_000_000, None], n_tr),
    "player_name": "Joueur",
})
transfers.to_csv(out / "transfers.csv", index=False)

n_val = 100
valuations = pd.DataFrame({
    "player_id": rng.integers(1, n_players + 1, n_val),
    "date": pd.to_datetime("2023-01-01") + pd.to_timedelta(rng.integers(0, 700, n_val), unit="D"),
    "market_value_in_eur": rng.choice([500_000, 2_000_000, None], n_val),
    "current_club_name": "Club",
    "current_club_id": rng.choice([1, 2], n_val),
    "player_club_domestic_competition_id": "FR1",
})
valuations.to_csv(out / "player_valuations.csv", index=False)

print("Fichiers synthétiques générés dans data/")
