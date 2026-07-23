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

    select p.id, p.active_version into v_plan_id, v_version
    from public.saved_plans p
    where p.user_id = p_user_id and p.ticker = upper(trim(p_ticker))
    for update;

    if exists (
        select 1 from public.saved_plan_versions pv where pv.saved_plan_id = v_plan_id
    ) then
        v_version := v_version + 1;
    else
        v_version := 1;
    end if;

    insert into public.saved_plan_versions (saved_plan_id, version, plan_data, analysis_timestamp)
    values (v_plan_id, v_version, p_plan_data, p_analysis_timestamp);

    update public.saved_plans p
    set active_version = v_version, updated_at = now()
    where p.id = v_plan_id;

    delete from public.price_alerts pa where pa.saved_plan_id = v_plan_id;

    return query
    select v_plan_id, upper(trim(p_ticker)), pv.version, pv.plan_data, pv.analysis_timestamp, pv.created_at
    from public.saved_plan_versions pv
    where pv.saved_plan_id = v_plan_id and pv.version = v_version;
end;
$$;

revoke all on function public.save_saved_plan_version(uuid, text, jsonb, timestamptz) from public, anon, authenticated;
grant execute on function public.save_saved_plan_version(uuid, text, jsonb, timestamptz) to service_role;
