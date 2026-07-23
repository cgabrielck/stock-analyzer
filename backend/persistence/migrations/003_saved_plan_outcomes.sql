create table if not exists public.saved_plan_outcomes (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.users(id) on delete cascade,
    saved_plan_id uuid not null,
    plan_version integer not null,
    horizon_days integer not null check (horizon_days in (5, 20, 60)),
    calculation_version integer not null default 1,
    outcome_data jsonb not null,
    evaluated_at timestamptz not null default now(),
    unique (saved_plan_id, plan_version, horizon_days, calculation_version),
    foreign key (saved_plan_id, plan_version)
        references public.saved_plan_versions(saved_plan_id, version) on delete cascade
);

create index if not exists saved_plan_outcomes_user_plan_idx
    on public.saved_plan_outcomes (user_id, saved_plan_id, plan_version, horizon_days);

alter table public.saved_plan_outcomes enable row level security;

create or replace function public.record_saved_plan_outcome(
    p_user_id uuid,
    p_saved_plan_id uuid,
    p_plan_version integer,
    p_outcome_data jsonb
)
returns setof public.saved_plan_outcomes
language plpgsql
security definer
set search_path = public
as $$
declare
    v_horizon integer := (p_outcome_data->>'horizon_days')::integer;
    v_calculation integer := coalesce((p_outcome_data->>'calculation_version')::integer, 1);
begin
    if v_horizon not in (5, 20, 60) then
        raise exception 'invalid outcome horizon';
    end if;
    if not exists (
        select 1 from public.saved_plans p
        join public.saved_plan_versions v on v.saved_plan_id = p.id
        where p.id = p_saved_plan_id and p.user_id = p_user_id and v.version = p_plan_version
    ) then
        raise exception 'saved plan version not found';
    end if;

    insert into public.saved_plan_outcomes (
        user_id, saved_plan_id, plan_version, horizon_days, calculation_version, outcome_data
    ) values (
        p_user_id, p_saved_plan_id, p_plan_version, v_horizon, v_calculation, p_outcome_data
    ) on conflict (saved_plan_id, plan_version, horizon_days, calculation_version) do nothing;

    return query
    select * from public.saved_plan_outcomes
    where saved_plan_id = p_saved_plan_id and plan_version = p_plan_version
      and horizon_days = v_horizon and calculation_version = v_calculation;
end;
$$;

revoke all on function public.record_saved_plan_outcome(uuid, uuid, integer, jsonb) from public, anon, authenticated;
grant execute on function public.record_saved_plan_outcome(uuid, uuid, integer, jsonb) to service_role;
