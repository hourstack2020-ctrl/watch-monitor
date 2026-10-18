CREATE TABLE public.comparison_reviews (
    pair_key text PRIMARY KEY,
    decision text NOT NULL CHECK(decision IN ('pending','approved','rejected')),
    details jsonb NOT NULL,
    reason text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen timestamptz NOT NULL DEFAULT now(),
    decided_at timestamptz
);
CREATE TABLE public.comparison_review_notifications (
    subscription_id text NOT NULL REFERENCES public.push_subscriptions(id) ON DELETE CASCADE,
    pair_key text NOT NULL REFERENCES public.comparison_reviews(pair_key) ON DELETE CASCADE,
    sent_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(subscription_id,pair_key)
);
ALTER TABLE public.comparison_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.comparison_review_notifications ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.comparison_reviews,public.comparison_review_notifications FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.comparison_reviews,public.comparison_review_notifications TO watch_monitor_app;
CREATE POLICY comparison_review_backend ON public.comparison_reviews FOR ALL TO watch_monitor_app USING(true) WITH CHECK(true);
CREATE POLICY comparison_review_notification_backend ON public.comparison_review_notifications FOR ALL TO watch_monitor_app USING(true) WITH CHECK(true);
CREATE INDEX comparison_reviews_pending ON public.comparison_reviews(last_seen) WHERE decision='pending';
