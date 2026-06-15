create or replace view public.vw_stay_night_history as
select
  r.*,
  m.market_name,
  coalesce(h.macro_group, m.macro_group) as effective_macro_group
from public.reservations_hackathon r
join public.market_code_lookup m
  on m.market_code = r.market_code
left join lateral (
  select hist.macro_group
  from public.market_macro_group_history hist
  where hist.market_code = r.market_code
    and r.stay_date >= hist.valid_from
    and (hist.valid_to is null or r.stay_date < hist.valid_to)
  order by hist.valid_from desc
  limit 1
) h on true;

create or replace view public.vw_stay_night_base as
select
  reservation_id,
  arrival_date,
  departure_date,
  stay_date,
  property_date,
  reservation_status,
  financial_status,
  create_datetime,
  cancellation_datetime,
  guest_country,
  is_block,
  is_walk_in,
  number_of_spaces,
  space_type,
  market_code,
  channel_code,
  source_name,
  rate_plan_code,
  daily_room_revenue_before_tax,
  daily_total_revenue_before_tax,
  nights,
  adr_room,
  lead_time,
  company_name,
  travel_agent_name,
  market_name,
  effective_macro_group
from public.vw_stay_night_history
where reservation_status <> 'Cancelled'
  and financial_status = 'Posted';

create or replace view public.vw_segment_stay_night as
select
  *
from public.vw_stay_night_base;

