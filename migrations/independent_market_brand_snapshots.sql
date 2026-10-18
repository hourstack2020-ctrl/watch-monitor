CREATE TABLE IF NOT EXISTS public.market_brand_snapshots (
    brand text PRIMARY KEY,
    observed_date date NOT NULL,
    checked_at timestamptz NOT NULL,
    count integer NOT NULL CHECK(count > 0),
    pages integer NOT NULL,
    source_count integer NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
ALTER TABLE public.market_brand_snapshots ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.market_brand_snapshots FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.market_brand_snapshots TO watch_monitor_app;
