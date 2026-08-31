# Data Warehouse & Pipeline Analytics — Football (Transfermarkt)

Pipeline complet : ingestion → contrôle qualité → constellation de faits → chargement PostgreSQL → dashboard interactif.

Dataset source : [Football Data from Transfermarkt](https://www.kaggle.com/datasets/davidcariboo/player-scores) (Kaggle).

## Structure du dépôt

```
.
├── sql/
│   └── schema.sql               # DDL PostgreSQL (constellation : 3 faits, 4 dimensions)
├── src/
│   ├── etl_pipeline.py          # Extraction, qualité, transformation, chargement
│   └── dashboard.py             # Dashboard Streamlit (5 KPI métier)
├── tests/
│   └── test_etl_pipeline.py     # 8 tests unitaires (règles qualité/transformation)
├── data/
│   └── generate_synthetic.py    # Génère un petit jeu de données de test
├── requirements.txt
└── README.md
```

## Prérequis

- Python 3.10+
- PostgreSQL 14+

```bash
pip install -r requirements.txt --break-system-packages   # ou dans un venv
```

## 1. Créer le schéma (une seule fois)

```bash
psql -h <host> -U <user> -d <db> -f sql/schema.sql
```

> `etl_pipeline.py` fait un `TRUNCATE ... CASCADE` puis recharge à chaque exécution — il ne recrée jamais les tables, pour préserver les contraintes de clés étrangères. `schema.sql` ne doit donc être exécuté qu'une fois.

## Alternative : lancer tout avec Docker

Un `docker-compose.yml` est fourni (PostgreSQL + ETL + dashboard + Adminer). Il évite d'installer PostgreSQL en local. **Testé de bout en bout sur les données réelles complètes** (voir section suivante pour les chiffres).

```bash
# 1. Placer les 6 CSV dans data/ (voir section suivante)
# 2. Démarrer PostgreSQL + Adminer (le schéma sql/schema.sql est appliqué automatiquement au premier démarrage)
docker compose up -d db adminer

# 3. Lancer le pipeline ETL (service à la demande, ne tourne pas avec `up`)
docker compose run --rm etl

# 4. Lancer le dashboard
docker compose up dashboard
# -> http://localhost:8501

# Pour tout arrêter :
docker compose down
# Pour repartir de zéro (efface aussi les données PostgreSQL) :
docker compose down -v
```

### Naviguer dans la base pendant la démo/présentation

Un service **Adminer** (interface web légère de navigation SQL, ~20 Mo, zéro config) est inclus dans `docker-compose.yml` pour explorer les tables et lancer des requêtes SQL en direct devant le jury, sans rien installer sur la machine :

```bash
docker compose up -d db adminer   # si pas déjà lancé
```

→ ouvrir **http://localhost:8080**, se connecter avec :

| Champ | Valeur |
|---|---|
| Système | PostgreSQL |
| Serveur | `db` |
| Utilisateur | `postgres` |
| Mot de passe | `postgres` |
| Base de données | `dw_football` |

Une fois connecté : cliquer sur le schéma `dw_foot` pour voir les 7 tables (4 dimensions, 3 faits), parcourir leur contenu ligne par ligne, ou utiliser l'onglet **SQL command** pour exécuter n'importe quelle requête (ex. la requête OLAP d'exemple en fin de `sql/schema.sql`) en direct.

## 2. Obtenir les données

Télécharger le dataset **Football Data from Transfermarkt** sur Kaggle et placer dans `data/` les 6 fichiers suivants (les autres ne sont pas utilisés — voir rapport, section 2.1) :

```
players.csv, clubs.csv, competitions.csv,
appearances.csv, transfers.csv, player_valuations.csv
```

⚠️ `appearances.csv` (~150 Mo) et `player_valuations.csv` (~32 Mo) sont volumineux — comptez quelques minutes pour le chargement complet. `game_lineups.csv` (336 Mo) n'est volontairement pas utilisé (cf. README racine du rapport).

Pour tester rapidement sans les vrais fichiers :

```bash
python data/generate_synthetic.py
```

## 3. Lancer le pipeline

```bash
python src/etl_pipeline.py \
  --data-dir data \
  --db-url postgresql://user:password@localhost:5432/dw \
  --today 2026-08-21
```

`--today` fixe la date de référence (utile pour reproduire des résultats identiques d'une exécution à l'autre ; par défaut, date du jour). Le rapport de qualité s'affiche dans les logs.

**Testé de bout en bout sur les données réelles complètes** : ~2,9M lignes sources, exécution en ~3 minutes, aucune erreur, contraintes FK vérifiées après chargement.

## 4. Lancer le dashboard

```bash
streamlit run src/dashboard.py -- --db-url postgresql://user:password@localhost:5432/dw
```

## Tests

```bash
pytest tests/ -v
```

8 tests couvrent : calcul de la saison football, calcul des tranches d'âge, gestion des FK orphelines (club → compétition inexistante), renommage des colonnes source, exclusion des joueurs orphelins dans Fact_Performances, exclusion des transferts à date future, exclusion des valorisations nulles.

## Anomalies réelles détectées (données complètes)

| Anomalie | Ampleur | Traitement |
|---|---|---|
| `competition_id` orphelin dans `appearances.csv` | 14 200 lignes (0,75 %) | Conservé, `id_competition` → NULL |
| Dates de transfert futures (jusqu'à 2030) | 492 transferts (0,28 %) | Exclus de Fact_Transferts |
| `total_market_value` (clubs.csv) | 100 % manquant | Colonne écartée du modèle |

## Limites connues

- Périmètre volontairement restreint à 6 fichiers sur 11 (voir rapport, section 2.1) — `games.csv`, `game_events.csv`, `club_games.csv`, `countries.csv`, `national_teams.csv` et `game_lineups.csv` sont hors scope pour les 5 questions métier retenues.
- La tranche d'âge est calculée par rapport à `--today`, pas par rapport à la date de chaque événement (simplification documentée dans le rapport, section 7.2).
