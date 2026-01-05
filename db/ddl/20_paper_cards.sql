-- Paper Cards Table Schema
-- Stores processed paper cards with enhanced schema fields

CREATE TABLE IF NOT EXISTS paper_cards (
    paper_id TEXT PRIMARY KEY,
    pmid TEXT,
    doi TEXT,
    
    -- Core metadata
    title TEXT,
    journal TEXT,
    year INTEGER,
    study_type TEXT,
    
    -- Population information
    population_size INTEGER,
    population_characteristics JSONB,
    
    -- Intervention details
    intervention_details JSONB,
    
    -- Outcomes and effect sizes
    outcome_measures JSONB,
    effect_sizes JSONB,
    
    -- Safety information
    safety_details JSONB,
    
    -- Quality metrics
    extraction_confidence FLOAT,
    study_quality_score FLOAT,
    
    -- Full card data
    full_card JSONB,
    
    -- Processing metadata
    processed_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_paper_cards_pmid ON paper_cards(pmid);
CREATE INDEX IF NOT EXISTS idx_paper_cards_doi ON paper_cards(doi);
CREATE INDEX IF NOT EXISTS idx_paper_cards_confidence ON paper_cards(extraction_confidence);
CREATE INDEX IF NOT EXISTS idx_paper_cards_quality ON paper_cards(study_quality_score);
CREATE INDEX IF NOT EXISTS idx_paper_cards_year ON paper_cards(year);
CREATE INDEX IF NOT EXISTS idx_paper_cards_study_type ON paper_cards(study_type);
CREATE INDEX IF NOT EXISTS idx_paper_cards_processed_at ON paper_cards(processed_at);

-- GIN indexes for JSONB fields
CREATE INDEX IF NOT EXISTS idx_paper_cards_population_gin ON paper_cards USING GIN (population_characteristics);
CREATE INDEX IF NOT EXISTS idx_paper_cards_intervention_gin ON paper_cards USING GIN (intervention_details);
CREATE INDEX IF NOT EXISTS idx_paper_cards_outcomes_gin ON paper_cards USING GIN (outcome_measures);
CREATE INDEX IF NOT EXISTS idx_paper_cards_effects_gin ON paper_cards USING GIN (effect_sizes);
CREATE INDEX IF NOT EXISTS idx_paper_cards_safety_gin ON paper_cards USING GIN (safety_details);
CREATE INDEX IF NOT EXISTS idx_paper_cards_full_card_gin ON paper_cards USING GIN (full_card);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_paper_cards_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to automatically update updated_at
CREATE TRIGGER trigger_update_paper_cards_updated_at
    BEFORE UPDATE ON paper_cards
    FOR EACH ROW
    EXECUTE FUNCTION update_paper_cards_updated_at();

-- Comments for documentation
COMMENT ON TABLE paper_cards IS 'Processed paper cards with enhanced schema for evidence-based supplement recommendations';
COMMENT ON COLUMN paper_cards.paper_id IS 'Unique identifier for the paper card';
COMMENT ON COLUMN paper_cards.pmid IS 'PubMed ID';
COMMENT ON COLUMN paper_cards.doi IS 'Digital Object Identifier';
COMMENT ON COLUMN paper_cards.population_size IS 'Number of participants in the study';
COMMENT ON COLUMN paper_cards.population_characteristics IS 'JSONB with age_mean, sex_distribution, training_status';
COMMENT ON COLUMN paper_cards.intervention_details IS 'JSONB with dose_g_per_day, duration_weeks, supplement_forms, etc.';
COMMENT ON COLUMN paper_cards.outcome_measures IS 'JSONB with strength, endurance, power outcomes';
COMMENT ON COLUMN paper_cards.effect_sizes IS 'JSONB array with effect sizes, p-values, confidence intervals';
COMMENT ON COLUMN paper_cards.safety_details IS 'JSONB with adverse_events, contraindications, safety_grade';
COMMENT ON COLUMN paper_cards.extraction_confidence IS 'Quality score (0-1) for extraction confidence';
COMMENT ON COLUMN paper_cards.study_quality_score IS 'Study quality score (1-10)';
COMMENT ON COLUMN paper_cards.full_card IS 'Complete card data as JSONB';
