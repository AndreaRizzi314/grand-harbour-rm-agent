create table if not exists public.room_type_lookup (
  space_type text primary key,
  room_class text not null,
  display_name text not null,
  number_of_rooms integer not null check (number_of_rooms >= 0)
);

create table if not exists public.rate_plan_lookup (
  rate_plan_code text primary key,
  plan_family text not null,
  is_commissionable boolean not null default false
);

create table if not exists public.market_code_lookup (
  market_code text primary key,
  market_name text not null,
  macro_group text not null,
  description text
);

create table if not exists public.market_macro_group_history (
  market_code text not null references public.market_code_lookup(market_code),
  valid_from date not null,
  valid_to date,
  macro_group text not null,
  primary key (market_code, valid_from),
  check (valid_to is null or valid_to > valid_from)
);

create table if not exists public.channel_code_lookup (
  channel_code text primary key,
  channel_name text not null,
  channel_group text not null
);

create table if not exists public.load_manifest (
  load_id bigint generated always as identity primary key,
  dataset_revision text not null,
  scraped_at timestamptz not null,
  source_url text not null,
  row_hash text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.reservations_hackathon (
  reservation_stay_id bigint generated always as identity primary key,
  reservation_id text not null,
  arrival_date date not null,
  departure_date date not null,
  stay_date date not null,
  property_date date not null,
  reservation_status text not null,
  financial_status text not null default 'Posted'
    check (financial_status in ('Posted', 'Provisional')),
  create_datetime timestamptz not null,
  cancellation_datetime timestamptz,
  guest_country text,
  is_block boolean not null default false,
  is_walk_in boolean not null default false,
  number_of_spaces integer not null check (number_of_spaces > 0),
  space_type text not null references public.room_type_lookup(space_type),
  market_code text not null references public.market_code_lookup(market_code),
  channel_code text not null references public.channel_code_lookup(channel_code),
  source_name text not null,
  rate_plan_code text not null references public.rate_plan_lookup(rate_plan_code),
  daily_room_revenue_before_tax numeric(10,2) not null default 0,
  daily_total_revenue_before_tax numeric(10,2) not null default 0,
  nights integer not null check (nights > 0),
  adr_room numeric(10,2) not null check (adr_room >= 0),
  lead_time integer not null check (lead_time >= 0),
  company_name text,
  travel_agent_name text,
  unique (reservation_id, stay_date)
);

create index if not exists idx_res_hackathon_stay_date
  on public.reservations_hackathon(stay_date);
create index if not exists idx_res_hackathon_property_date
  on public.reservations_hackathon(property_date);
create index if not exists idx_res_hackathon_create_datetime
  on public.reservations_hackathon(create_datetime);
create index if not exists idx_res_hackathon_market_code
  on public.reservations_hackathon(market_code);
create index if not exists idx_res_hackathon_channel_code
  on public.reservations_hackathon(channel_code);
create index if not exists idx_res_hackathon_reservation_status
  on public.reservations_hackathon(reservation_status);
create index if not exists idx_res_hackathon_financial_status
  on public.reservations_hackathon(financial_status);
create index if not exists idx_market_macro_history_dates
  on public.market_macro_group_history(market_code, valid_from, valid_to);
