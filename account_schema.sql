CREATE TABLE IF NOT EXISTS public.admin_account (singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton), username text NOT NULL, password_hash text NOT NULL, auth_version text NOT NULL, failed_attempts integer NOT NULL DEFAULT 0, locked_until timestamptz, updated_at timestamptz NOT NULL DEFAULT now());
ALTER TABLE public.admin_account ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.admin_account FROM PUBLIC, anon, authenticated;

GRANT SELECT,INSERT,UPDATE ON public.admin_account TO watch_monitor_app;
CREATE POLICY backend_account_access ON public.admin_account FOR ALL TO watch_monitor_app USING (true) WITH CHECK (true);
