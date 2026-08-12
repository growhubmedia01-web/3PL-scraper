-- =====================================================================
-- Row Level Security (section 53)
-- Backend uses the service_role key and bypasses RLS.
-- The frontend uses the publishable/anon key and gets read-only access
-- to non-personal tables only. Decision makers stay server-side.
-- =====================================================================

alter table services              enable row level security;
alter table service_signals       enable row level security;
alter table service_keywords      enable row level security;
alter table discovery_queries     enable row level security;
alter table service_roles         enable row level security;
alter table companies             enable row level security;
alter table sources               enable row level security;
alter table crawl_jobs            enable row level security;
alter table signals               enable row level security;
alter table service_opportunities enable row level security;
alter table decision_makers       enable row level security;
alter table suppressions          enable row level security;
alter table search_cache          enable row level security;
alter table pipeline_runs         enable row level security;
alter table api_usage             enable row level security;
alter table lead_reviews          enable row level security;

-- Authenticated users may read the lead-facing tables.
do $$
declare t text;
begin
  foreach t in array array['services','service_signals','service_keywords',
                           'companies','sources','signals',
                           'service_opportunities','pipeline_runs']
  loop
    execute format(
      'drop policy if exists "auth_read_%1$s" on %1$s;
       create policy "auth_read_%1$s" on %1$s
       for select to authenticated using (true);', t);
  end loop;
end $$;

-- Decision makers contain personal data: read requires an authenticated
-- session, and rows for suppressed people/domains are filtered out.
drop policy if exists "auth_read_decision_makers" on decision_makers;
create policy "auth_read_decision_makers" on decision_makers
for select to authenticated
using (
  not exists (
    select 1 from suppressions s
    where (s.kind = 'person' and lower(s.value) = lower(decision_makers.name))
       or (s.kind = 'domain' and exists (
             select 1 from companies c
             where c.id = decision_makers.company_id
               and lower(c.domain) = lower(s.value)))
  )
);

-- Human review: authenticated users may label leads.
drop policy if exists "auth_write_lead_reviews" on lead_reviews;
create policy "auth_write_lead_reviews" on lead_reviews
for all to authenticated using (true) with check (true);

-- Everything else (crawl_jobs, api_usage, search_cache, suppressions,
-- discovery_queries, service_roles) has NO policy => service_role only.

-- Anonymous access is granted nowhere. Never expose the service_role key
-- to the browser.
