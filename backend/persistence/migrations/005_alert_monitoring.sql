alter table public.price_alerts
    add column if not exists armed boolean not null default true,
    add column if not exists last_price numeric(20, 6),
    add column if not exists last_quote_time timestamptz,
    add column if not exists last_triggered_at timestamptz;

update public.price_alerts
set monitoring_enabled = true, armed = true
where monitoring_enabled = false;

create table if not exists public.alert_events (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.users(id) on delete cascade,
    price_alert_id uuid not null references public.price_alerts(id) on delete cascade,
    saved_plan_id uuid not null references public.saved_plans(id) on delete cascade,
    plan_version integer not null,
    ticker text not null,
    event_type text not null,
    price numeric(20, 6) not null,
    quote_time timestamptz not null,
    event_data jsonb not null default '{}'::jsonb,
    idempotency_key text not null unique,
    created_at timestamptz not null default now(),
    read_at timestamptz
);

create index if not exists alert_events_user_created_idx
    on public.alert_events (user_id, created_at desc);

alter table public.alert_events enable row level security;

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
        select 1 from public.saved_plans p
        where p.id = p_saved_plan_id and p.user_id = p_user_id and p.active_version = p_plan_version
    ) then
        raise exception 'saved plan not found or version is not active';
    end if;
    delete from public.price_alerts pa where pa.saved_plan_id = p_saved_plan_id;
    insert into public.price_alerts (
        user_id, saved_plan_id, plan_version, event_type, rule_data,
        monitoring_enabled, armed
    )
    select p_user_id, p_saved_plan_id, p_plan_version,
        item->>'event_type', item->'rule_data', true, true
    from jsonb_array_elements(p_rules) item;
    return query
    select pa.* from public.price_alerts pa
    where pa.saved_plan_id = p_saved_plan_id order by pa.event_type;
end;
$$;

create or replace function public.record_alert_evaluation(
    p_alert_id uuid,
    p_price numeric,
    p_quote_time timestamptz,
    p_armed boolean,
    p_triggered boolean,
    p_idempotency_key text,
    p_event_data jsonb
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
    v_alert public.price_alerts%rowtype;
    v_ticker text;
begin
    select * into v_alert from public.price_alerts where id = p_alert_id for update;
    if not found then
        raise exception 'price alert not found';
    end if;
    select ticker into v_ticker from public.saved_plans where id = v_alert.saved_plan_id;

    update public.price_alerts
    set armed = p_armed, last_price = p_price, last_quote_time = p_quote_time,
        last_triggered_at = case when p_triggered then now() else last_triggered_at end,
        updated_at = now()
    where id = p_alert_id;

    if p_triggered then
        insert into public.alert_events (
            user_id, price_alert_id, saved_plan_id, plan_version, ticker, event_type,
            price, quote_time, event_data, idempotency_key
        ) values (
            v_alert.user_id, v_alert.id, v_alert.saved_plan_id, v_alert.plan_version,
            v_ticker, v_alert.event_type, p_price, p_quote_time, p_event_data, p_idempotency_key
        ) on conflict (idempotency_key) do nothing;
    end if;
end;
$$;

revoke all on function public.record_alert_evaluation(uuid, numeric, timestamptz, boolean, boolean, text, jsonb) from public, anon, authenticated;
grant execute on function public.record_alert_evaluation(uuid, numeric, timestamptz, boolean, boolean, text, jsonb) to service_role;
revoke all on function public.replace_plan_alert_rules(uuid, uuid, integer, jsonb) from public, anon, authenticated;
grant execute on function public.replace_plan_alert_rules(uuid, uuid, integer, jsonb) to service_role;
