-- Esquema de producción: PostgreSQL 16 + TimescaleDB.
-- SQLAlchemy crea las tablas (Base.metadata.create_all); este script agrega las
-- extensiones de series temporales. Ejecutar una vez luego del primer arranque:
--   psql "$DATABASE_URL" -f app/db/timescale.sql

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Timescale exige que la columna temporal forme parte de toda clave única.
-- Reemplazamos la PK sustituta por una compuesta antes de crear las hypertables.
ALTER TABLE price_bars DROP CONSTRAINT IF EXISTS price_bars_pkey;
ALTER TABLE price_bars ADD PRIMARY KEY (instrument_id, market, day, id);
SELECT create_hypertable('price_bars', 'day', migrate_data => true, if_not_exists => true,
                         chunk_time_interval => INTERVAL '180 days');

ALTER TABLE fx_rates DROP CONSTRAINT IF EXISTS fx_rates_pkey;
ALTER TABLE fx_rates ADD PRIMARY KEY (kind, day, id);
SELECT create_hypertable('fx_rates', 'day', migrate_data => true, if_not_exists => true);

ALTER TABLE score_snapshots DROP CONSTRAINT IF EXISTS score_snapshots_pkey;
ALTER TABLE score_snapshots ADD PRIMARY KEY (instrument_id, day, id);
SELECT create_hypertable('score_snapshots', 'day', migrate_data => true, if_not_exists => true);

-- Compresión de chunks antiguos (las barras diarias no se reescriben).
ALTER TABLE price_bars SET (timescaledb.compress, timescaledb.compress_segmentby = 'instrument_id, market');
SELECT add_compression_policy('price_bars', INTERVAL '90 days', if_not_exists => true);

-- Agregado continuo: CCL semanal promedio (para gráficos de largo plazo).
CREATE MATERIALIZED VIEW IF NOT EXISTS ccl_weekly
WITH (timescaledb.continuous) AS
SELECT time_bucket('7 days', day) AS week, avg(value) AS ccl_avg, min(value) AS ccl_min, max(value) AS ccl_max
FROM fx_rates WHERE kind = 'CCL'
GROUP BY week;
