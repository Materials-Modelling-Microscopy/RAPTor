-- Alloy Assistant relational schema
-- Dialect: DuckDB
-- Status: draft DDL; this file does not create a database by itself.

-- DuckDB does not support foreign keys across SQL schemas. All relational
-- tables therefore live in one `alloy` schema so referential integrity remains
-- enforceable. The section headings below preserve the conceptual layers.
CREATE SCHEMA IF NOT EXISTS alloy;

-- ---------------------------------------------------------------------------
-- Provenance
-- ---------------------------------------------------------------------------

CREATE TABLE alloy.sources (
    source_id VARCHAR PRIMARY KEY,
    source_class VARCHAR NOT NULL CHECK (
        source_class IN (
            'external_literature',
            'own_publication',
            'manuscript',
            'dissertation',
            'experimental_dataset',
            'computational_dataset',
            'thermodynamic_database',
            'code',
            'research_note'
        )
    ),
    title VARCHAR NOT NULL,
    original_path VARCHAR NOT NULL,
    sha256 VARCHAR NOT NULL UNIQUE,
    version_label VARCHAR,
    confidentiality VARCHAR NOT NULL CHECK (
        confidentiality IN (
            'public',
            'internal',
            'unpublished',
            'licensed',
            'restricted'
        )
    ),
    authority_status VARCHAR NOT NULL CHECK (
        authority_status IN (
            'authoritative',
            'authoritative_curated',
            'supporting',
            'provisional'
        )
    ),
    citation VARCHAR,
    registered_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    notes VARCHAR
);

-- ---------------------------------------------------------------------------
-- Elements, systems, and compositions
-- ---------------------------------------------------------------------------

CREATE TABLE alloy.elements (
    element_symbol VARCHAR PRIMARY KEY,
    atomic_number INTEGER NOT NULL UNIQUE CHECK (atomic_number > 0),
    element_name VARCHAR NOT NULL UNIQUE
);

CREATE TABLE alloy.alloy_systems (
    system_id VARCHAR PRIMARY KEY,
    canonical_name VARCHAR NOT NULL UNIQUE,
    n_components INTEGER NOT NULL CHECK (n_components >= 2)
);

CREATE TABLE alloy.alloy_system_elements (
    system_id VARCHAR NOT NULL REFERENCES alloy.alloy_systems(system_id),
    element_symbol VARCHAR NOT NULL REFERENCES alloy.elements(element_symbol),
    PRIMARY KEY (system_id, element_symbol)
);

CREATE TABLE alloy.compositions (
    composition_id VARCHAR PRIMARY KEY,
    system_id VARCHAR NOT NULL REFERENCES alloy.alloy_systems(system_id),
    canonical_formula VARCHAR NOT NULL,
    original_formula VARCHAR,
    basis VARCHAR NOT NULL DEFAULT 'atomic_fraction' CHECK (
        basis IN ('atomic_fraction', 'weight_fraction', 'unknown')
    ),
    is_equimolar BOOLEAN NOT NULL,
    source_id VARCHAR NOT NULL REFERENCES alloy.sources(source_id),
    source_locator VARCHAR,
    UNIQUE (system_id, canonical_formula, source_id, source_locator)
);

CREATE TABLE alloy.composition_components (
    composition_id VARCHAR NOT NULL
        REFERENCES alloy.compositions(composition_id),
    element_symbol VARCHAR NOT NULL
        REFERENCES alloy.elements(element_symbol),
    fraction DOUBLE NOT NULL CHECK (fraction >= 0 AND fraction <= 1),
    PRIMARY KEY (composition_id, element_symbol)
);

CREATE TABLE alloy.element_melting_points (
    element_symbol VARCHAR NOT NULL REFERENCES alloy.elements(element_symbol),
    melting_temperature_K DOUBLE NOT NULL CHECK (
        melting_temperature_K > 0
    ),
    source_id VARCHAR NOT NULL REFERENCES alloy.sources(source_id),
    PRIMARY KEY (element_symbol, source_id)
);

-- This view is evaluated when queried; the derived value is not duplicated.
CREATE OR REPLACE VIEW alloy.composition_weighted_melting_temperatures AS
SELECT
    cc.composition_id,
    sum(cc.fraction * emp.melting_temperature_K)
        / nullif(sum(cc.fraction), 0)
        AS melting_temperature_K
FROM alloy.composition_components AS cc
JOIN alloy.element_melting_points AS emp
    USING (element_symbol)
GROUP BY cc.composition_id;

-- ---------------------------------------------------------------------------
-- Models and reproducible runs
-- ---------------------------------------------------------------------------

CREATE TABLE alloy.models (
    model_id VARCHAR PRIMARY KEY,
    model_name VARCHAR NOT NULL,
    model_version VARCHAR NOT NULL,
    description VARCHAR,
    code_source_id VARCHAR REFERENCES alloy.sources(source_id),
    UNIQUE (model_name, model_version)
);

CREATE TABLE alloy.calculation_runs (
    run_id VARCHAR PRIMARY KEY,
    model_id VARCHAR NOT NULL REFERENCES alloy.models(model_id),
    composition_id VARCHAR REFERENCES alloy.compositions(composition_id),
    system_id VARCHAR REFERENCES alloy.alloy_systems(system_id),
    tdb_source_id VARCHAR REFERENCES alloy.sources(source_id),
    result_source_id VARCHAR NOT NULL REFERENCES alloy.sources(source_id),
    settings_json JSON,
    run_timestamp TIMESTAMP,
    CHECK (
        (composition_id IS NOT NULL AND system_id IS NULL)
        OR
        (composition_id IS NULL AND system_id IS NOT NULL)
    )
);

CREATE TABLE alloy.pairwise_interactions (
    interaction_id VARCHAR PRIMARY KEY,
    model_id VARCHAR NOT NULL REFERENCES alloy.models(model_id),
    element_a VARCHAR NOT NULL REFERENCES alloy.elements(element_symbol),
    element_b VARCHAR NOT NULL REFERENCES alloy.elements(element_symbol),
    interaction_type VARCHAR NOT NULL DEFAULT 'mixing_enthalpy_0K',
    value_eV_atom DOUBLE NOT NULL,
    source_id VARCHAR NOT NULL REFERENCES alloy.sources(source_id),
    CHECK (element_a < element_b),
    UNIQUE (
        model_id,
        element_a,
        element_b,
        interaction_type,
        source_id
    )
);

CREATE TABLE alloy.miscibility_predictions (
    prediction_id VARCHAR PRIMARY KEY,
    run_id VARCHAR NOT NULL REFERENCES alloy.calculation_runs(run_id),
    composition_id VARCHAR NOT NULL
        REFERENCES alloy.compositions(composition_id),
    reported_miscibility_temperature_K DOUBLE NOT NULL CHECK (
        reported_miscibility_temperature_K >= 0
    ),
    miscibility_temperature_K DOUBLE NOT NULL CHECK (
        miscibility_temperature_K > 0
    ),
    normalization_rule VARCHAR NOT NULL CHECK (
        normalization_rule IN ('none', 'zero_to_room_temperature')
    ),
    legacy_melting_temperature_K DOUBLE CHECK (
        legacy_melting_temperature_K > 0
    ),
    source_row_number INTEGER NOT NULL CHECK (source_row_number > 0),
    quality_flag VARCHAR NOT NULL DEFAULT 'unreviewed',
    UNIQUE (run_id, composition_id)
);

CREATE OR REPLACE VIEW alloy.miscibility_prediction_metrics AS
SELECT
    mp.prediction_id,
    mp.run_id,
    mp.composition_id,
    mp.reported_miscibility_temperature_K,
    mp.miscibility_temperature_K,
    cwmt.melting_temperature_K,
    mp.miscibility_temperature_K
        / nullif(cwmt.melting_temperature_K, 0)
        AS miscibility_ratio,
    mp.legacy_melting_temperature_K,
    mp.normalization_rule,
    mp.quality_flag
FROM alloy.miscibility_predictions AS mp
LEFT JOIN alloy.composition_weighted_melting_temperatures AS cwmt
    USING (composition_id);

CREATE TABLE alloy.pmr_predictions (
    pmr_prediction_id VARCHAR PRIMARY KEY,
    run_id VARCHAR NOT NULL REFERENCES alloy.calculation_runs(run_id),
    system_id VARCHAR NOT NULL REFERENCES alloy.alloy_systems(system_id),
    temperature_K DOUBLE NOT NULL CHECK (temperature_K > 0),
    pmr_percent DOUBLE NOT NULL CHECK (
        pmr_percent >= 0 AND pmr_percent <= 100
    ),
    grid_spacing_atomic_fraction DOUBLE NOT NULL DEFAULT 0.1 CHECK (
        grid_spacing_atomic_fraction > 0
        AND grid_spacing_atomic_fraction <= 1
    ),
    source_row_number INTEGER NOT NULL CHECK (source_row_number > 0),
    quality_flag VARCHAR NOT NULL DEFAULT 'unreviewed',
    UNIQUE (run_id, system_id, temperature_K)
);

-- ---------------------------------------------------------------------------
-- Phases and experimental validation
-- ---------------------------------------------------------------------------

CREATE TABLE alloy.phases (
    phase_id VARCHAR PRIMARY KEY,
    canonical_name VARCHAR NOT NULL UNIQUE,
    phase_family VARCHAR,
    notes VARCHAR
);

CREATE TABLE alloy.phase_aliases (
    raw_label VARCHAR PRIMARY KEY,
    phase_id VARCHAR REFERENCES alloy.phases(phase_id),
    mapping_status VARCHAR NOT NULL CHECK (
        mapping_status IN ('reviewed', 'provisional', 'unresolved')
    )
);

CREATE TABLE alloy.predicted_phase_fractions (
    phase_fraction_id VARCHAR PRIMARY KEY,
    run_id VARCHAR NOT NULL REFERENCES alloy.calculation_runs(run_id),
    composition_id VARCHAR NOT NULL
        REFERENCES alloy.compositions(composition_id),
    temperature_K DOUBLE NOT NULL CHECK (temperature_K > 0),
    phase_id VARCHAR REFERENCES alloy.phases(phase_id),
    raw_phase_label VARCHAR NOT NULL,
    phase_fraction DOUBLE CHECK (
        phase_fraction >= 0 AND phase_fraction <= 1
    ),
    source_locator VARCHAR,
    UNIQUE (
        run_id,
        composition_id,
        temperature_K,
        raw_phase_label
    )
);

CREATE TABLE alloy.experimental_samples (
    sample_id VARCHAR PRIMARY KEY,
    composition_id VARCHAR NOT NULL
        REFERENCES alloy.compositions(composition_id),
    source_id VARCHAR NOT NULL REFERENCES alloy.sources(source_id),
    source_locator VARCHAR,
    sample_label VARCHAR,
    provenance_status VARCHAR NOT NULL CHECK (
        provenance_status IN (
            'complete',
            'publication_mapping_pending',
            'unknown'
        )
    )
);

CREATE TABLE alloy.processing_events (
    processing_event_id VARCHAR PRIMARY KEY,
    sample_id VARCHAR NOT NULL
        REFERENCES alloy.experimental_samples(sample_id),
    sequence_number INTEGER NOT NULL CHECK (sequence_number > 0),
    route VARCHAR NOT NULL,
    temperature_K DOUBLE CHECK (temperature_K > 0),
    duration_s DOUBLE CHECK (duration_s > 0),
    cooling_rate_K_s DOUBLE CHECK (cooling_rate_K_s > 0),
    raw_processing_label VARCHAR,
    notes VARCHAR,
    UNIQUE (sample_id, sequence_number)
);

CREATE TABLE alloy.experimental_phase_observations (
    observation_id VARCHAR PRIMARY KEY,
    sample_id VARCHAR NOT NULL
        REFERENCES alloy.experimental_samples(sample_id),
    phase_id VARCHAR REFERENCES alloy.phases(phase_id),
    raw_phase_label VARCHAR NOT NULL,
    phase_fraction DOUBLE CHECK (
        phase_fraction >= 0 AND phase_fraction <= 1
    ),
    characterization_method VARCHAR,
    observation_temperature_K DOUBLE CHECK (
        observation_temperature_K > 0
    ),
    source_locator VARCHAR
);

-- TDB files are initially versioned assets, not decomposed parameter tables.
CREATE TABLE alloy.thermodynamic_databases (
    tdb_id VARCHAR PRIMARY KEY,
    source_id VARCHAR NOT NULL UNIQUE REFERENCES alloy.sources(source_id),
    system_id VARCHAR NOT NULL REFERENCES alloy.alloy_systems(system_id),
    software_compatibility VARCHAR,
    parameter_count INTEGER CHECK (parameter_count >= 0),
    phase_count INTEGER CHECK (phase_count >= 0)
);

-- ---------------------------------------------------------------------------
-- Literature RAG metadata
-- ---------------------------------------------------------------------------

CREATE TABLE alloy.documents (
    document_id VARCHAR PRIMARY KEY,
    source_id VARCHAR NOT NULL UNIQUE REFERENCES alloy.sources(source_id),
    title VARCHAR,
    authors VARCHAR,
    publication_year INTEGER,
    doi VARCHAR,
    page_count INTEGER CHECK (page_count > 0),
    parse_status VARCHAR NOT NULL CHECK (
        parse_status IN ('pending', 'parsed', 'reviewed', 'failed')
    )
);

CREATE TABLE alloy.document_chunks (
    chunk_id VARCHAR PRIMARY KEY,
    document_id VARCHAR NOT NULL
        REFERENCES alloy.documents(document_id),
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    section_title VARCHAR,
    page_start INTEGER CHECK (page_start > 0),
    page_end INTEGER CHECK (page_end > 0),
    chunk_text VARCHAR NOT NULL,
    parser_version VARCHAR NOT NULL,
    UNIQUE (document_id, chunk_index),
    CHECK (
        page_start IS NULL
        OR page_end IS NULL
        OR page_end >= page_start
    )
);

CREATE TABLE alloy.chunk_entities (
    chunk_id VARCHAR NOT NULL
        REFERENCES alloy.document_chunks(chunk_id),
    entity_type VARCHAR NOT NULL CHECK (
        entity_type IN ('element', 'alloy_system', 'phase', 'method', 'concept')
    ),
    entity_value VARCHAR NOT NULL,
    PRIMARY KEY (chunk_id, entity_type, entity_value)
);

-- Embeddings are generated, replaceable retrieval artifacts. FLOAT[384]
-- matches the initial BGE-small model; model identity and text checksum make
-- regeneration explicit and prevent vectors from silently outliving chunks.
CREATE TABLE alloy.chunk_embeddings (
    embedding_id VARCHAR PRIMARY KEY,
    chunk_id VARCHAR NOT NULL
        REFERENCES alloy.document_chunks(chunk_id),
    model_name VARCHAR NOT NULL,
    model_revision VARCHAR NOT NULL,
    embedding_dimension INTEGER NOT NULL CHECK (
        embedding_dimension = 384
    ),
    text_sha256 VARCHAR NOT NULL,
    embedding FLOAT[384] NOT NULL,
    normalized BOOLEAN NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    UNIQUE (chunk_id, model_name, model_revision)
);
