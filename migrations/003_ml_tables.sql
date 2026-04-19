-- Migration 003: ML prediction log + market signals tables
-- Run once against valuations_institutional

CREATE TABLE IF NOT EXISTS market_signals (
    id              SERIAL PRIMARY KEY,
    ticker          VARCHAR(20) NOT NULL,
    collected_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    collected_date  DATE NOT NULL DEFAULT CURRENT_DATE,
    analyst_target_mean     FLOAT,
    analyst_target_median   FLOAT,
    analyst_target_high     FLOAT,
    analyst_target_low      FLOAT,
    analyst_count           INTEGER,
    recommendation_mean     FLOAT,
    forward_eps             FLOAT,
    forward_pe              FLOAT,
    forward_revenue_growth  FLOAT,
    implied_growth_rate     FLOAT,
    sentiment_score         FLOAT,     -- reserved for FinBERT (Phase 2)
    CONSTRAINT uq_market_signals_ticker_date UNIQUE (ticker, collected_date)
);

CREATE INDEX IF NOT EXISTS idx_market_signals_ticker ON market_signals(ticker);
CREATE INDEX IF NOT EXISTS idx_market_signals_collected ON market_signals(collected_at DESC);


CREATE TABLE IF NOT EXISTS prediction_log (
    id              SERIAL PRIMARY KEY,
    ticker          VARCHAR(20) NOT NULL,
    predicted_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    predicted_price FLOAT NOT NULL,
    model_version   VARCHAR(20) NOT NULL DEFAULT 'v2',
    company_type    VARCHAR(40),
    sub_sector_tag  VARCHAR(40),
    blend_weights   JSONB,
    dcf_price       FLOAT,
    ev_price        FLOAT,
    pe_price        FLOAT,
    analyst_target  FLOAT,
    wacc            FLOAT,
    growth_y1       FLOAT,
    ebitda_method   VARCHAR(20),
    -- Outcome fields — filled in by outcome_tracker job
    actual_price_30d    FLOAT,
    actual_price_90d    FLOAT,
    actual_price_180d   FLOAT,
    actual_price_365d   FLOAT,
    outcome_updated_at  TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_prediction_log_ticker ON prediction_log(ticker);
CREATE INDEX IF NOT EXISTS idx_prediction_log_predicted ON prediction_log(predicted_at DESC);
CREATE INDEX IF NOT EXISTS idx_prediction_log_outcome ON prediction_log(actual_price_365d)
    WHERE actual_price_365d IS NULL;
