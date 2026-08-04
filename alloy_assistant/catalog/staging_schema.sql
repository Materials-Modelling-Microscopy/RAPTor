-- Faithful landing tables for source files.
--
-- Staging tables preserve source values and source row numbers. They do not
-- use cross-schema foreign keys because DuckDB does not support them.

CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE IF NOT EXISTS staging.binary_equimolar_data_raw (
    source_id VARCHAR NOT NULL,
    source_row_number INTEGER NOT NULL CHECK (source_row_number > 1),
    source_index INTEGER NOT NULL,
    alloy_name VARCHAR NOT NULL,
    melting_temperature_K DOUBLE NOT NULL,
    reported_miscibility_temperature_K DOUBLE NOT NULL,
    hmix_eV_atom DOUBLE NOT NULL,
    decomposition_at_melting_raw VARCHAR NOT NULL,
    decomposition_at_miscibility_raw VARCHAR NOT NULL,
    legacy_miscibility_ratio DOUBLE NOT NULL,
    experimental_temperature_K_raw DOUBLE,
    PRIMARY KEY (source_id, source_row_number)
);

CREATE TABLE IF NOT EXISTS staging.equimolar_data_raw (
    source_id VARCHAR NOT NULL,
    source_row_number INTEGER NOT NULL CHECK (source_row_number > 1),
    source_index INTEGER NOT NULL,
    n_components INTEGER NOT NULL CHECK (n_components BETWEEN 3 AND 5),
    alloy_name VARCHAR NOT NULL,
    melting_temperature_K DOUBLE NOT NULL,
    reported_miscibility_temperature_K DOUBLE NOT NULL,
    pair_columns_json JSON NOT NULL,
    legacy_mean_hmix_eV_atom DOUBLE NOT NULL,
    decomposition_at_melting_raw VARCHAR NOT NULL,
    decomposition_at_miscibility_raw VARCHAR NOT NULL,
    legacy_miscibility_ratio DOUBLE NOT NULL,
    PRIMARY KEY (source_id, source_row_number)
);

CREATE TABLE IF NOT EXISTS staging.pmr_data_raw (
    source_id VARCHAR NOT NULL,
    source_row_number INTEGER NOT NULL CHECK (source_row_number > 1),
    source_index INTEGER NOT NULL,
    n_components INTEGER NOT NULL CHECK (n_components BETWEEN 2 AND 5),
    alloy_name VARCHAR NOT NULL,
    pmr_500K_percent DOUBLE NOT NULL,
    pmr_1000K_percent DOUBLE NOT NULL,
    pmr_1500K_percent DOUBLE NOT NULL,
    legacy_condition DOUBLE,
    PRIMARY KEY (source_id, source_row_number)
);

CREATE TABLE IF NOT EXISTS staging.experimental_validation_raw (
    source_id VARCHAR NOT NULL,
    source_row_number INTEGER NOT NULL CHECK (source_row_number > 1),
    composition_raw VARCHAR,
    reported_phases_raw VARCHAR,
    processing_raw VARCHAR,
    processing_temperature_K DOUBLE,
    predicted_miscibility_temperature_K DOUBLE,
    trailing_empty_raw VARCHAR,
    row_status VARCHAR NOT NULL CHECK (
        row_status IN ('substantive', 'non_data')
    ),
    PRIMARY KEY (source_id, source_row_number)
);

CREATE TABLE IF NOT EXISTS staging.tdb_registry_raw (
    source_id VARCHAR PRIMARY KEY,
    file_name VARCHAR NOT NULL,
    canonical_system_name VARCHAR NOT NULL,
    n_components INTEGER NOT NULL CHECK (n_components BETWEEN 2 AND 6),
    phase_count INTEGER NOT NULL CHECK (phase_count >= 0),
    parameter_count INTEGER NOT NULL CHECK (parameter_count >= 0)
);
