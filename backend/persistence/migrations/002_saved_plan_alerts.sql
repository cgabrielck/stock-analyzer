create table if not exists public.price_alerts (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.users(id) on delete cascade,
    saved_plan_id uuid not null references public.saved_plans(id) on delete cascade,
    plan_version integer not null,
    event_type text not null check (event_type in ('entry_zone', 'confirmation', 'stop', 'target_1', 'target_2')),
    rule_data jsonb not null,
    monitoring_enabled boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (saved_plan_id, event_type)
);

alter table public.price_alerts enable row level security;

create or replace function public.save_saved_plan_version(
    p_user_id uuid,
    p_ticker text,
    p_plan_data jsonb,
    p_analysis_timestamp timestamptz
)
returns table (
    plan_id uuid,
    ticker text,
    version integer,
    plan_data jsonb,
    analysis_timestamp timestamptz,
    created_at timestamptz
)
language plpgsql
security definer
set search_path = public
as $$
declare
    v_plan_id uuid;
    v_version integer;
begin
    perform pg_advisory_xact_lock(hashtextextended(p_user_id::text || ':' || upper(trim(p_ticker)), 0));

    insert into public.saved_plans (user_id, ticker)
    values (p_user_id, upper(trim(p_ticker)))
    on conflict on constraint saved_plans_user_id_ticker_key do nothing;

    select id, active_version into v_plan_id, v_version
    from public.saved_plans
    where user_id = p_user_id and saved_plans.ticker = upper(trim(p_ticker))
    for update;

    if exists (select 1 from public.saved_plan_versions where saved_plan_id = v_plan_id) then
        v_version := v_version + 1;
    else
        v_version := 1;
    end if;

    insert into public.saved_plan_versions (saved_plan_id, version, plan_data, analysis_timestamp)
    values (v_plan_id, v_version, p_plan_data, p_analysis_timestamp);

    update public.saved_plans
    set active_version = v_version, updated_at = now()
    where id = v_plan_id;

    -- Alert levels belong to a specific plan version and require explicit reconfirmation.
    delete from public.price_alerts where saved_plan_id = v_plan_id;

    return query
    select v_plan_id, upper(trim(p_ticker)), v.version, v.plan_data, v.analysis_timestamp, v.created_at
    from public.saved_plan_versions v
    where v.saved_plan_id = v_plan_id and v.version = v_version;
end;
$$;

create or replace function public.replace_plan_alert_rules(
    p_user_id uuid,
    p_saved_plan_id uuid,
    p_plan_version integer,
    p_rules jsonb
)
returns setof public.price_alerts
language plpgsql
security definer
set search_path = public
as $$
begin
    if not exists (
        select 1 from public.saved_plans
        where id = p_saved_plan_id and user_id = p_user_id and active_version = p_plan_version
    ) then
        raise exception 'saved plan not found or version is not active';
    end if;

    delete from public.price_alerts where saved_plan_id = p_saved_plan_id;

    insert into public.price_alerts (
        user_id, saved_plan_id, plan_version, event_type, rule_data, monitoring_enabled
    )
    select
        p_user_id, p_saved_plan_id, p_plan_version,
        item->>'event_type', item->'rule_data', false
    from jsonb_array_elements(p_rules) item;

    return query
    select * from public.price_alerts where saved_plan_id = p_saved_plan_id order by event_type;
end;
$$;

revoke all on function public.save_saved_plan_version(uuid, text, jsonb, timestamptz) from public, anon, authenticated;
revoke all on function public.replace_plan_alert_rules(uuid, uuid, integer, jsonb) from public, anon, authenticated;
grant execute on function public.save_saved_plan_version(uuid, text, jsonb, timestamptz) to service_role;
grant execute on function public.replace_plan_alert_rules(uuid, uuid, integer, jsonb) to service_role;
