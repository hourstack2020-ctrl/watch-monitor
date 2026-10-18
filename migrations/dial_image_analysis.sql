CREATE TABLE public.dial_image_analysis (
    image_url text PRIMARY KEY,
    analyzer_version integer NOT NULL,
    checked_at timestamptz NOT NULL DEFAULT now(),
    result jsonb NOT NULL
);
ALTER TABLE public.dial_image_analysis ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.dial_image_analysis FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.dial_image_analysis TO watch_monitor_app;
CREATE POLICY dial_image_backend ON public.dial_image_analysis
    FOR ALL TO watch_monitor_app USING (true) WITH CHECK (true);
