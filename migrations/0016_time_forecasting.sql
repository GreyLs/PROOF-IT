-- Displayed company signal used by the local time-to-fill forecast.  It is
-- intentionally bounded and defaults to a neutral value for existing firms.
ALTER TABLE companies ADD COLUMN IF NOT EXISTS market_rating numeric(2,1) NOT NULL DEFAULT 4.2 CHECK(market_rating>=1.0 AND market_rating<=5.0);
