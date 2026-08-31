-- Data Warehouse Football (Transfermarkt) — Fact Constellation
-- PostgreSQL

DROP SCHEMA IF EXISTS dw_foot CASCADE;
CREATE SCHEMA dw_foot;

-- ============ DIMENSIONS PARTAGEES ============

CREATE TABLE dw_foot.dim_date (
    id_date        SERIAL PRIMARY KEY,
    date_complete  DATE NOT NULL UNIQUE,
    jour           SMALLINT NOT NULL,
    mois           SMALLINT NOT NULL,
    trimestre      SMALLINT NOT NULL,
    annee          SMALLINT NOT NULL,
    saison_football VARCHAR(10) NOT NULL  -- ex: '2023/2024' (juillet->juin)
);

CREATE TABLE dw_foot.dim_competition (
    id_competition   VARCHAR(10) PRIMARY KEY,
    nom              VARCHAR(150),
    type             VARCHAR(50),
    confederation    VARCHAR(50)
);

CREATE TABLE dw_foot.dim_club (
    id_club                  INT PRIMARY KEY,
    nom                      VARCHAR(150),
    stade                    VARCHAR(150),
    taille_effectif          INT,
    age_moyen                NUMERIC(4,1),
    competition_domestique   VARCHAR(10) REFERENCES dw_foot.dim_competition(id_competition)
);

CREATE TABLE dw_foot.dim_joueur (
    id_joueur                  INT PRIMARY KEY,
    nom                        VARCHAR(150),
    position                   VARCHAR(50),
    sous_position              VARCHAR(50),
    pied                       VARCHAR(20),
    taille_cm                  INT,
    date_naissance             DATE,
    tranche_age                VARCHAR(20),
    pays_naissance              VARCHAR(100),
    nationalite                VARCHAR(100),
    valeur_marchande_actuelle  NUMERIC(14,2),
    valeur_marchande_max       NUMERIC(14,2)
);

-- ============ FAITS ============

-- Grain: une ligne = une apparition d'un joueur dans un match
CREATE TABLE dw_foot.fact_performances (
    id_performance   VARCHAR(30) PRIMARY KEY,   -- appearance_id source (conservé tel quel)
    id_date          INT NOT NULL REFERENCES dw_foot.dim_date(id_date),
    id_joueur        INT NOT NULL REFERENCES dw_foot.dim_joueur(id_joueur),
    id_club          INT REFERENCES dw_foot.dim_club(id_club),
    id_competition   VARCHAR(10) REFERENCES dw_foot.dim_competition(id_competition),
    id_match         BIGINT NOT NULL,           -- dimension dégénérée (game_id source)
    buts             INT NOT NULL DEFAULT 0,
    passes_decisives INT NOT NULL DEFAULT 0,
    cartons_jaunes   INT NOT NULL DEFAULT 0,
    cartons_rouges   INT NOT NULL DEFAULT 0,
    minutes_jouees   INT NOT NULL DEFAULT 0
);

-- Grain: une ligne = un transfert de joueur
CREATE TABLE dw_foot.fact_transferts (
    id_transfert              BIGSERIAL PRIMARY KEY,
    id_date                   INT NOT NULL REFERENCES dw_foot.dim_date(id_date),
    id_joueur                 INT NOT NULL REFERENCES dw_foot.dim_joueur(id_joueur),
    id_club_origine            INT REFERENCES dw_foot.dim_club(id_club),
    id_club_destination        INT REFERENCES dw_foot.dim_club(id_club),
    saison_transfert           VARCHAR(10),
    montant_transfert          NUMERIC(14,2),
    valeur_marchande_estimee   NUMERIC(14,2)
);

-- Grain: une ligne = un relevé de valeur marchande d'un joueur à une date
CREATE TABLE dw_foot.fact_valorisations (
    id_valorisation   BIGSERIAL PRIMARY KEY,
    id_date           INT NOT NULL REFERENCES dw_foot.dim_date(id_date),
    id_joueur         INT NOT NULL REFERENCES dw_foot.dim_joueur(id_joueur),
    id_club           INT REFERENCES dw_foot.dim_club(id_club),
    valeur_marchande  NUMERIC(14,2) NOT NULL
);

CREATE INDEX idx_perf_joueur ON dw_foot.fact_performances(id_joueur);
CREATE INDEX idx_perf_date   ON dw_foot.fact_performances(id_date);
CREATE INDEX idx_perf_comp   ON dw_foot.fact_performances(id_competition);
CREATE INDEX idx_trans_joueur ON dw_foot.fact_transferts(id_joueur);
CREATE INDEX idx_val_joueur   ON dw_foot.fact_valorisations(id_joueur);
CREATE INDEX idx_val_date     ON dw_foot.fact_valorisations(id_date);

-- Exemple de requête OLAP (Q2) : Top buteurs+passeurs par saison et compétition
-- SELECT d.saison_football, c.nom AS competition, j.nom, SUM(f.buts) AS buts, SUM(f.passes_decisives) AS passes
-- FROM dw_foot.fact_performances f
-- JOIN dw_foot.dim_date d ON f.id_date = d.id_date
-- JOIN dw_foot.dim_joueur j ON f.id_joueur = j.id_joueur
-- JOIN dw_foot.dim_competition c ON f.id_competition = c.id_competition
-- GROUP BY d.saison_football, c.nom, j.nom
-- ORDER BY d.saison_football DESC, buts DESC;
