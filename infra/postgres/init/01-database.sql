-- Se ejecuta una sola vez, al crear el volumen pgdata por primera vez.
-- Convención 3.1: todas las marcas de tiempo en UTC.
DO $$
BEGIN
    EXECUTE format('ALTER DATABASE %I SET timezone TO %L', current_database(), 'UTC');
END
$$;
-- gen_random_uuid() es nativo desde PostgreSQL 13; no se requiere pgcrypto.
