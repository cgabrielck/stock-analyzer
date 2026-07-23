create extension if not exists pgcrypto;

create table if not exists public.users (
    id uuid primary key default gen_random_uuid(),
    username text not null,
    normalized_username text not null unique,
    pin text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.user_sessions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.users(id) on delete cascade,
    token_hash text not null unique,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    revoked_at timestamptz
);

create table if not exists public.user_preferences (
    user_id uuid primary key references public.users(id) on delete cascade,
    schema_version integer not null default 1,
    language text not null default 'zh_tw' check (language in ('zh_cn', 'zh_tw', 'en')),
    portfolio_capital integer not null default 100000 check (portfolio_capital between 1000 and 10000000),
    risk_budget_pct numeric(4,2) not null default 1.0 check (risk_budget_pct between 0.1 and 5.0),
    include_ai_news boolean not null default true,
    updated_at timestamptz not null default now()
);

create table if not exists public.favorites (
    user_id uuid not null references public.users(id) on delete cascade,
    ticker text not null,
    created_at timestamptz not null default now(),
    primary key (user_id, ticker)
);

create table if not exists public.saved_plans (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.users(id) on delete cascade,
    ticker text not null,
    active_version integer not null default 1,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (user_id, ticker)
);

create table if not exists public.saved_plan_versions (
    id uuid primary key default gen_random_uuid(),
    saved_plan_id uuid not null references public.saved_plans(id) on delete cascade,
    version integer not null,
    plan_data jsonb not null,
    analysis_timestamp timestamptz not null,
    created_at timestamptz not null default now(),
    unique (saved_plan_id, version)
);

alter table public.users enable row level security;
alter table public.user_sessions enable row level security;
alter table public.user_preferences enable row level security;
alter table public.favorites enable row level security;
alter table public.saved_plans enable row level security;
alter table public.saved_plan_versions enable row level security;

-- Custom auth is handled only by trusted server-side code using the service-role key.
-- No anon/authenticated policies are created, so direct public API access fails closed.
